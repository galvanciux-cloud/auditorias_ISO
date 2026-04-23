"""
audit_engine.py — Motor central del agente de auditoría ISO 27001.

Responsabilidades:
  1. Construir los system prompts y prompts de evaluación.
  2. Hacer preguntas al usuario en consola sobre cada control.
  3. Enviar la respuesta a la IA para evaluación estructurada (JSON).
  4. Convertir la respuesta JSON en un Finding y pasarlo al MemoryManager.
  5. Implementar el flujo de "cadena de pensamiento" para una evaluación rigurosa.
"""

import logging
from typing import List, Optional

from config import Config
from knowledge_base import KnowledgeBase
from llm_router import LLMRouter, LLMParseError
from memory_manager import AuditState, Finding, MemoryManager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Controles del Anexo A (ISO 27001:2022) — lista de referencia interna
# Se usa cuando NO se han cargado documentos externos.
# ──────────────────────────────────────────────────────────────────────────────

ANNEX_A_CONTROLS = {
    # Cláusula 5 — Controles Organizacionales
    "A.5.1":  "Políticas de Seguridad de la Información",
    "A.5.2":  "Roles y Responsabilidades de Seguridad de la Información",
    "A.5.3":  "Segregación de Funciones",
    "A.5.4":  "Responsabilidades de la Dirección",
    "A.5.5":  "Contacto con Autoridades",
    "A.5.6":  "Contacto con Grupos de Interés Especial",
    "A.5.7":  "Inteligencia de Amenazas",
    "A.5.8":  "Seguridad de la Información en la Gestión de Proyectos",
    "A.5.9":  "Inventario de Activos de Información",
    "A.5.10": "Uso Aceptable de Activos",
    "A.5.11": "Devolución de Activos",
    "A.5.12": "Clasificación de la Información",
    "A.5.13": "Etiquetado de la Información",
    "A.5.14": "Transferencia de Información",
    "A.5.15": "Control de Acceso",
    "A.5.16": "Gestión de Identidad",
    "A.5.17": "Información de Autenticación",
    "A.5.18": "Derechos de Acceso",
    "A.5.19": "Seguridad de la Información en Relaciones con Proveedores",
    "A.5.20": "Acuerdos de Seguridad con Proveedores",
    "A.5.21": "Seguridad de la Información en la Cadena de Suministro TIC",
    "A.5.22": "Monitorización y Revisión de Servicios de Proveedores",
    "A.5.23": "Seguridad en Servicios Cloud",
    "A.5.24": "Planificación de la Gestión de Incidentes",
    "A.5.25": "Evaluación de Eventos de SI",
    "A.5.26": "Respuesta a Incidentes de SI",
    "A.5.27": "Aprendizaje de Incidentes de SI",
    "A.5.28": "Recopilación de Evidencias",
    "A.5.29": "Continuidad del Negocio en Incidentes",
    "A.5.30": "Preparación TIC para Continuidad del Negocio",
    "A.5.31": "Requisitos Legales, Estatutarios y Reglamentarios",
    "A.5.32": "Derechos de Propiedad Intelectual",
    "A.5.33": "Protección de Registros",
    "A.5.34": "Privacidad y Protección de Datos Personales",
    "A.5.35": "Revisión Independiente de la SI",
    "A.5.36": "Cumplimiento de Políticas y Normas",
    "A.5.37": "Procedimientos Operativos Documentados",
    # Cláusula 6 — Controles de Personas
    "A.6.1":  "Selección de Personal",
    "A.6.2":  "Términos y Condiciones del Empleo",
    "A.6.3":  "Concienciación, Educación y Formación en SI",
    "A.6.4":  "Proceso Disciplinario",
    "A.6.5":  "Responsabilidades al Término del Empleo",
    "A.6.6":  "Acuerdos de Confidencialidad o No Divulgación",
    "A.6.7":  "Trabajo Remoto",
    "A.6.8":  "Reporte de Eventos de SI",
    # Cláusula 7 — Controles Físicos
    "A.7.1":  "Perímetros de Seguridad Física",
    "A.7.2":  "Controles de Entrada Física",
    "A.7.3":  "Seguridad de Oficinas, Despachos e Instalaciones",
    "A.7.4":  "Monitorización de Seguridad Física",
    "A.7.5":  "Protección contra Amenazas Físicas y Ambientales",
    "A.7.6":  "Trabajo en Áreas Seguras",
    "A.7.7":  "Escritorio y Pantalla Limpios",
    "A.7.8":  "Ubicación y Protección de Equipos",
    "A.7.9":  "Seguridad de Activos fuera de las Instalaciones",
    "A.7.10": "Medios de Almacenamiento",
    "A.7.11": "Suministros de Apoyo (Utilities)",
    "A.7.12": "Seguridad del Cableado",
    "A.7.13": "Mantenimiento de Equipos",
    "A.7.14": "Eliminación Segura o Reutilización de Equipos",
    # Cláusula 8 — Controles Tecnológicos
    "A.8.1":  "Dispositivos de Usuario Final",
    "A.8.2":  "Derechos de Acceso Privilegiado",
    "A.8.3":  "Restricción de Acceso a la Información",
    "A.8.4":  "Acceso al Código Fuente",
    "A.8.5":  "Autenticación Segura",
    "A.8.6":  "Gestión de la Capacidad",
    "A.8.7":  "Protección contra Malware",
    "A.8.8":  "Gestión de Vulnerabilidades Técnicas",
    "A.8.9":  "Gestión de la Configuración",
    "A.8.10": "Eliminación de Información",
    "A.8.11": "Enmascaramiento de Datos",
    "A.8.12": "Prevención de Fuga de Datos",
    "A.8.13": "Copias de Seguridad (Backup)",
    "A.8.14": "Redundancia de Instalaciones de Procesamiento",
    "A.8.15": "Registro de Eventos (Logging)",
    "A.8.16": "Actividades de Monitorización",
    "A.8.17": "Sincronización de Relojes",
    "A.8.18": "Uso de Programas de Utilidades Privilegiados",
    "A.8.19": "Instalación de Software en Sistemas en Producción",
    "A.8.20": "Seguridad en Redes",
    "A.8.21": "Seguridad de los Servicios de Red",
    "A.8.22": "Segregación de Redes",
    "A.8.23": "Filtrado Web",
    "A.8.24": "Uso de Criptografía",
    "A.8.25": "Ciclo de Vida del Desarrollo Seguro",
    "A.8.26": "Requisitos de Seguridad en Aplicaciones",
    "A.8.27": "Principios de Arquitectura y Sistemas Seguros",
    "A.8.28": "Codificación Segura",
    "A.8.29": "Pruebas de Seguridad en Desarrollo y Aceptación",
    "A.8.30": "Desarrollo Externalizado",
    "A.8.31": "Separación de Entornos (Desarrollo/Pruebas/Producción)",
    "A.8.32": "Gestión del Cambio",
    "A.8.33": "Información de Prueba",
    "A.8.34": "Protección de Sistemas de Información durante Pruebas de Auditoría",
}


# ──────────────────────────────────────────────────────────────────────────────
# System prompt para el rol de auditor
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un auditor experto en ISO 27001:2022, certificado como Lead Auditor.
Tu función es evaluar de forma objetiva y rigurosa las respuestas del auditado 
sobre la implementación de controles de seguridad.

REGLAS ESTRICTAS:
1. Evalúa ÚNICAMENTE basándote en la evidencia proporcionada y el texto del control ISO.
2. NO inventes hallazgos. Si la información es insuficiente, solicita evidencias específicas.
3. Usa terminología técnica ISO 27001 (conformidad, no conformidad, observación, evidencia objetiva).
4. Sé directo, técnico y no paternalista.
5. SIEMPRE responde en formato JSON válido con EXACTAMENTE estos campos:
   {
     "estado": "<Conforme|No Conforme|Observación|No Aplicable>",
     "hallazgo": "<descripción técnica del hallazgo, citando el control ISO>",
     "evidencia_requerida": "<qué documentos/registros/pruebas se necesitan para cerrar el hallazgo>",
     "brecha_encontrada": "<qué falta implementar o qué está mal implementado; N/A si es Conforme>",
     "pregunta_followup": "<pregunta de profundización si se necesita más información; null si no>",
     "nivel_riesgo": "<Alto|Medio|Bajo|No Aplica>"
   }
6. No incluyas texto fuera del JSON. No uses bloques ```json. Solo el objeto JSON puro.
"""


# ──────────────────────────────────────────────────────────────────────────────
# AuditEngine
# ──────────────────────────────────────────────────────────────────────────────

class AuditEngine:
    """
    Motor de auditoría: orquesta el flujo de preguntas, evaluación IA y registro.
    """

    def __init__(
        self,
        llm: LLMRouter,
        kb: KnowledgeBase,
        memory: MemoryManager,
    ) -> None:
        self.llm = llm
        self.kb = kb
        self.memory = memory

    def get_controls_to_audit(self) -> List[str]:
        """
        Retorna la lista de controles del Anexo A.
        Si el KB tiene controles indexados, los usa; si no, usa la lista interna.
        """
        kb_controls = self.kb.get_all_control_ids()
        if kb_controls:
            logger.info("Usando %d controles del Knowledge Base.", len(kb_controls))
            return kb_controls
        logger.info("Usando lista interna de %d controles ISO 27001:2022.", len(ANNEX_A_CONTROLS))
        return list(ANNEX_A_CONTROLS.keys())

    def get_control_title(self, control_id: str) -> str:
        """Obtiene el título de un control desde el KB o la lista interna."""
        return ANNEX_A_CONTROLS.get(control_id, f"Control {control_id}")

    def build_evaluation_prompt(
        self,
        control_id: str,
        control_title: str,
        iso_context: str,
        user_response: str,
        organization: str,
    ) -> str:
        """
        Construye el prompt de evaluación con inyección de contexto inteligente.
        Solo incluye el fragmento del control relevante, no todo el documento.
        """
        return f"""
CONTROL ISO 27001 A EVALUAR:
Control: {control_id} — {control_title}
Organización auditada: {organization}

TEXTO DEL CONTROL (extraído del documento ISO):
---
{iso_context}
---

RESPUESTA DEL AUDITADO:
"{user_response}"

INSTRUCCIONES:
Evalúa si la respuesta del auditado demuestra implementación efectiva del control {control_id}.
Considera:
- Existencia de políticas/procedimientos documentados
- Implementación técnica o administrativa de los controles
- Evidencia objetiva disponible
- Brechas de cumplimiento respecto al requisito normativo

Responde ÚNICAMENTE con el objeto JSON definido en tus instrucciones de sistema.
""".strip()

    def build_question_prompt(
        self,
        control_id: str,
        control_title: str,
        iso_context: str,
        organization: str,
    ) -> str:
        """
        Genera la pregunta de auditoría que se mostrará al usuario.
        Esta llamada a la IA produce texto libre (no JSON).
        """
        return f"""
Eres un auditor ISO 27001. Debes formular UNA pregunta de auditoría abierta y técnica 
para verificar el cumplimiento del siguiente control en la organización "{organization}".

Control: {control_id} — {control_title}

Contexto del control:
---
{iso_context[:1500]}
---

Formula la pregunta de manera que:
1. Sea específica y orientada a obtener evidencia objetiva.
2. Pida describir el PROCESO actual, no solo si existe o no.
3. Use terminología ISO 27001.
4. Sea una sola pregunta clara (máximo 3 líneas).

Solo escribe la pregunta. Sin introducción ni explicación.
""".strip()

    def generate_audit_question(
        self, control_id: str, iso_context: str, organization: str
    ) -> str:
        """Pide a la IA que genere una pregunta de auditoría para el control."""
        title = self.get_control_title(control_id)
        prompt = self.build_question_prompt(control_id, title, iso_context, organization)
        try:
            question = self.llm.generate(prompt, system_prompt=None)
            return question.strip()
        except Exception as exc:
            logger.error("Error generando pregunta para %s: %s", control_id, exc)
            # Pregunta genérica de fallback
            return (
                f"¿Puede describir cómo su organización implementa el control {control_id} "
                f"({title})? Indique los procedimientos, responsables y evidencias disponibles."
            )

    def evaluate_response(
        self,
        control_id: str,
        user_response: str,
        iso_context: str,
        organization: str,
        followup_count: int = 0,
    ) -> Optional[Finding]:
        """
        Evalúa la respuesta del usuario mediante la IA y retorna un Finding.

        Implementa cadena de pensamiento:
          1. Envía contexto ISO + respuesta a la IA.
          2. Parsea el JSON de evaluación.
          3. Si hay pregunta de seguimiento y aún no se han hecho 2, la formula.
          4. Retorna el Finding final.
        """
        title = self.get_control_title(control_id)
        prompt = self.build_evaluation_prompt(
            control_id, title, iso_context, user_response, organization
        )

        try:
            result = self.llm.generate_json(prompt, system_prompt=SYSTEM_PROMPT)
        except LLMParseError as exc:
            logger.error("JSON inválido en evaluación de %s: %s", control_id, exc)
            # Crear hallazgo de error para no perder la sesión
            return Finding(
                control_id=control_id,
                title=title,
                estado="Observación",
                hallazgo="Error al procesar la evaluación automática. Revisión manual requerida.",
                evidencia_requerida="Revisar manualmente según el control ISO.",
                brecha_encontrada="No determinado automáticamente.",
                respuesta_usuario=user_response,
            )

        # Validar y sanitizar campos del JSON
        estado = result.get("estado", "Observación")
        if estado not in Finding.VALID_STATES:
            estado = "Observación"

        finding = Finding(
            control_id=control_id,
            title=title,
            estado=estado,
            hallazgo=result.get("hallazgo", "Sin descripción."),
            evidencia_requerida=result.get("evidencia_requerida", "No especificada."),
            brecha_encontrada=result.get("brecha_encontrada", "N/A"),
            respuesta_usuario=user_response,
        )

        # Guardar nivel de riesgo como parte del hallazgo
        nivel_riesgo = result.get("nivel_riesgo", "")
        if nivel_riesgo and nivel_riesgo != "No Aplica":
            finding.hallazgo += f" [Riesgo: {nivel_riesgo}]"

        # Pregunta de seguimiento (máximo 2 iteraciones)
        followup = result.get("pregunta_followup")
        if followup and followup_count < 2:
            return self._handle_followup(
                finding, followup, control_id, iso_context, organization, followup_count
            )

        return finding

    def _handle_followup(
        self,
        preliminary_finding: Finding,
        followup_question: str,
        control_id: str,
        iso_context: str,
        organization: str,
        followup_count: int,
    ) -> Finding:
        """Gestiona preguntas de seguimiento en consola y re-evalúa."""
        print(f"\n  🔍 Pregunta de seguimiento #{followup_count + 1}:")
        print(f"  {followup_question}")
        print()
        user_response = input("  ➜ Su respuesta: ").strip()

        if not user_response:
            logger.info("Usuario omitió pregunta de seguimiento para %s.", control_id)
            return preliminary_finding

        # Combinar respuesta original + seguimiento para re-evaluación
        combined_response = (
            f"[Respuesta inicial]: {preliminary_finding.respuesta_usuario}\n"
            f"[Información adicional]: {user_response}"
        )

        return self.evaluate_response(
            control_id=control_id,
            user_response=combined_response,
            iso_context=iso_context,
            organization=organization,
            followup_count=followup_count + 1,
        )

    def run_control_audit(self, control_id: str) -> Optional[Finding]:
        """
        Ejecuta el ciclo completo de auditoría para UN control:
          1. Obtiene contexto ISO del KB.
          2. Genera pregunta con IA.
          3. Muestra pregunta al usuario y recoge respuesta.
          4. Evalúa con IA.
          5. Muestra resultado y retorna Finding.
        """
        organization = self.memory.state.organization
        iso_context = self.kb.get_context_for_control(control_id)
        title = self.get_control_title(control_id)

        print(f"\n{'─'*70}")
        print(f"🔎 CONTROL: {control_id} — {title}")
        print(f"{'─'*70}")

        # Generar y mostrar pregunta
        print("  ⏳ Generando pregunta de auditoría...")
        question = self.generate_audit_question(control_id, iso_context, organization)
        print(f"\n  📋 {question}\n")

        # Recoger respuesta del usuario
        print("  (Escriba su respuesta. Presione Enter dos veces para finalizar,")
        print("   o escriba 'omitir' para marcar como No Aplicable)\n")

        lines = []
        try:
            while True:
                line = input("  ➜ ")
                if line.strip().lower() == "omitir":
                    justification = input("  Justificación de exclusión: ").strip()
                    self.memory.mark_not_applicable(control_id, title, justification)
                    print(f"\n  ➖ Control {control_id} marcado como No Aplicable.")
                    return self.memory.get_finding(control_id)
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except KeyboardInterrupt:
            print("\n  ⚠️  Sesión interrumpida. El progreso ha sido guardado.")
            return None

        user_response = "\n".join(lines).strip()
        if not user_response:
            print("  ⚠️  No se proporcionó respuesta. Control omitido temporalmente.")
            return None

        # Evaluar con IA
        print("\n  🤖 Evaluando respuesta...")
        finding = self.evaluate_response(
            control_id=control_id,
            user_response=user_response,
            iso_context=iso_context,
            organization=organization,
        )

        if finding:
            self.memory.add_finding(finding)
            self._display_finding(finding)

        return finding

    def _display_finding(self, finding: Finding) -> None:
        """Muestra el resultado de la evaluación en consola."""
        emoji = {"Conforme": "✅", "No Conforme": "❌",
                 "Observación": "⚠️", "No Aplicable": "➖"}.get(finding.estado, "❓")
        print(f"\n  {emoji} RESULTADO: {finding.estado}")
        print(f"  📝 Hallazgo: {finding.hallazgo}")
        if finding.brecha_encontrada and finding.brecha_encontrada != "N/A":
            print(f"  🔴 Brecha: {finding.brecha_encontrada}")
        print(f"  📎 Evidencia requerida: {finding.evidencia_requerida}")
