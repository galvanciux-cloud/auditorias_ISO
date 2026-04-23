"""
memory_manager.py — Persistencia del estado de la auditoría en Markdown.

El archivo estado_auditoria.md actúa como "memoria" del agente:
  - Se crea al iniciar una nueva auditoría.
  - Se actualiza en tiempo real tras cada evaluación de control.
  - Se lee al arrancar para reanudar auditorías pausadas.

Estructura del archivo:
  # Estado de Auditoría ISO 27001
  ## Metadatos
  ## Controles Evaluados
  ### A.x.y — Título
  **Estado:** Conforme | No Conforme | Observación
  **Hallazgo:** ...
  **Evidencia requerida:** ...
  **Fecha:** ...
  ## Controles Pendientes
  ## Resumen de Hallazgos
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Modelos de datos simples (sin dependencias externas)
# ──────────────────────────────────────────────────────────────────────────────

class Finding:
    """Representa el hallazgo de un control auditado."""

    VALID_STATES = ("Conforme", "No Conforme", "Observación", "No Aplicable")

    def __init__(
        self,
        control_id: str,
        title: str,
        estado: str,
        hallazgo: str,
        evidencia_requerida: str,
        brecha_encontrada: str,
        respuesta_usuario: str = "",
        fecha: Optional[str] = None,
    ) -> None:
        self.control_id = control_id.upper()
        self.title = title
        self.estado = estado if estado in self.VALID_STATES else "Observación"
        self.hallazgo = hallazgo
        self.evidencia_requerida = evidencia_requerida
        self.brecha_encontrada = brecha_encontrada
        self.respuesta_usuario = respuesta_usuario
        self.fecha = fecha or datetime.now().strftime("%Y-%m-%d %H:%M")

    def to_markdown(self) -> str:
        emoji = {"Conforme": "✅", "No Conforme": "❌",
                 "Observación": "⚠️", "No Aplicable": "➖"}.get(self.estado, "❓")
        return (
            f"### {self.control_id} — {self.title}\n"
            f"**Estado:** {emoji} {self.estado}  \n"
            f"**Fecha:** {self.fecha}  \n"
            f"**Respuesta del auditado:** {self.respuesta_usuario}  \n"
            f"**Hallazgo:** {self.hallazgo}  \n"
            f"**Evidencia requerida:** {self.evidencia_requerida}  \n"
            f"**Brecha encontrada:** {self.brecha_encontrada}  \n"
        )


class AuditState:
    """Estado completo de la auditoría en memoria."""

    def __init__(
        self,
        organization: str = "",
        auditor: str = "",
        start_date: str = "",
    ) -> None:
        self.organization = organization or Config.ORGANIZATION_NAME
        self.auditor = auditor or Config.AUDITOR_NAME
        self.start_date = start_date or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.findings: Dict[str, Finding] = {}       # control_id → Finding
        self.pending_controls: List[str] = []         # controles aún sin auditar
        self.scope_notes: str = ""                    # notas de alcance


# ──────────────────────────────────────────────────────────────────────────────
# Clase MemoryManager
# ──────────────────────────────────────────────────────────────────────────────

class MemoryManager:
    """Lee, actualiza y persiste el archivo estado_auditoria.md."""

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.state_file = state_file or Config.STATE_FILE
        self.state = AuditState()

    # ── Persistencia ──────────────────────────────────────────────

    def save(self) -> None:
        """Escribe el estado completo en el archivo Markdown."""
        content = self._build_markdown()
        self.state_file.write_text(content, encoding="utf-8")
        logger.debug("Estado guardado en %s", self.state_file)

    def load(self) -> bool:
        """
        Lee el archivo de estado si existe y repopula self.state.
        Retorna True si se cargó una auditoría previa, False si es nueva.
        """
        if not self.state_file.exists():
            logger.info("No existe %s. Iniciando nueva auditoría.", self.state_file)
            return False

        try:
            content = self.state_file.read_text(encoding="utf-8")
            self._parse_markdown(content)
            logger.info(
                "Auditoría cargada: %d controles evaluados, %d pendientes.",
                len(self.state.findings),
                len(self.state.pending_controls),
            )
            return True
        except Exception as exc:
            logger.error("Error leyendo %s: %s. Se inicia sesión nueva.", self.state_file, exc)
            return False

    # ── Operaciones sobre el estado ───────────────────────────────

    def add_finding(self, finding: Finding) -> None:
        """Agrega o actualiza un hallazgo y lo persiste inmediatamente."""
        self.state.findings[finding.control_id] = finding
        # Remover de pendientes si estaba
        self.state.pending_controls = [
            c for c in self.state.pending_controls if c != finding.control_id
        ]
        self.save()
        logger.info("Hallazgo registrado: %s → %s", finding.control_id, finding.estado)

    def set_pending_controls(self, controls: List[str]) -> None:
        """Define la lista de controles pendientes (solo los que aún no tienen hallazgo)."""
        already_done = set(self.state.findings.keys())
        self.state.pending_controls = [c for c in controls if c not in already_done]
        self.save()

    def get_next_pending(self) -> Optional[str]:
        """Retorna el siguiente control pendiente o None si todos están evaluados."""
        return self.state.pending_controls[0] if self.state.pending_controls else None

    def mark_not_applicable(self, control_id: str, title: str, justification: str) -> None:
        """Marca un control como No Aplicable con una justificación."""
        finding = Finding(
            control_id=control_id,
            title=title,
            estado="No Aplicable",
            hallazgo=f"Control excluido del alcance: {justification}",
            evidencia_requerida="N/A",
            brecha_encontrada="N/A",
        )
        self.add_finding(finding)

    def initialize_new_audit(
        self,
        organization: str,
        auditor: str,
        scope_notes: str = "",
    ) -> None:
        """Inicializa una nueva auditoría, borrando el estado anterior."""
        self.state = AuditState(organization=organization, auditor=auditor)
        self.state.scope_notes = scope_notes
        self.save()
        logger.info("Nueva auditoría iniciada para: %s", organization)

    # ── Consultas ─────────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, int]:
        """Devuelve un resumen estadístico de la auditoría."""
        totals: Dict[str, int] = {
            "Conforme": 0,
            "No Conforme": 0,
            "Observación": 0,
            "No Aplicable": 0,
            "Pendiente": len(self.state.pending_controls),
        }
        for f in self.state.findings.values():
            if f.estado in totals:
                totals[f.estado] += 1
        return totals

    def is_control_done(self, control_id: str) -> bool:
        return control_id.upper() in self.state.findings

    def get_finding(self, control_id: str) -> Optional[Finding]:
        return self.state.findings.get(control_id.upper())

    def get_all_findings(self) -> List[Finding]:
        return list(self.state.findings.values())

    def get_non_conformities(self) -> List[Finding]:
        return [f for f in self.state.findings.values() if f.estado == "No Conforme"]

    def get_observations(self) -> List[Finding]:
        return [f for f in self.state.findings.values() if f.estado == "Observación"]

    # ── Serialización / Deserialización Markdown ───────────────────

    def _build_markdown(self) -> str:
        """Construye el contenido Markdown del archivo de estado."""
        stats = self.get_statistics()
        lines: List[str] = [
            "# Estado de Auditoría ISO 27001",
            "",
            "## Metadatos",
            f"- **Organización:** {self.state.organization}",
            f"- **Auditor:** {self.state.auditor}",
            f"- **Inicio:** {self.state.start_date}",
            f"- **Última actualización:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"- **Alcance:** {self.state.scope_notes or 'Por definir'}",
            "",
            "## Resumen de Hallazgos",
            f"- ✅ Conformes: {stats['Conforme']}",
            f"- ❌ No Conformes: {stats['No Conforme']}",
            f"- ⚠️  Observaciones: {stats['Observación']}",
            f"- ➖ No Aplicables: {stats['No Aplicable']}",
            f"- 🕐 Pendientes: {stats['Pendiente']}",
            "",
        ]

        # Controles evaluados
        if self.state.findings:
            lines.append("## Controles Evaluados")
            lines.append("")
            for finding in sorted(self.state.findings.values(), key=lambda f: f.control_id):
                lines.append(finding.to_markdown())
                lines.append("")

        # Controles pendientes
        if self.state.pending_controls:
            lines.append("## Controles Pendientes")
            lines.append("")
            for ctrl in self.state.pending_controls:
                lines.append(f"- [ ] {ctrl}")
            lines.append("")

        return "\n".join(lines)

    def _parse_markdown(self, content: str) -> None:
        """
        Parsea el archivo Markdown y restaura el estado en memoria.
        Extrae metadatos y hallazgos usando expresiones regulares simples.
        """
        # Metadatos
        org_match = re.search(r"\*\*Organización:\*\*\s*(.+)", content)
        aud_match = re.search(r"\*\*Auditor:\*\*\s*(.+)", content)
        ini_match = re.search(r"\*\*Inicio:\*\*\s*(.+)", content)
        scp_match = re.search(r"\*\*Alcance:\*\*\s*(.+)", content)

        if org_match:
            self.state.organization = org_match.group(1).strip()
        if aud_match:
            self.state.auditor = aud_match.group(1).strip()
        if ini_match:
            self.state.start_date = ini_match.group(1).strip()
        if scp_match:
            self.state.scope_notes = scp_match.group(1).strip()

        # Hallazgos — buscar bloques ### A.x.y
        block_pattern = re.compile(
            r"### (A[\d.]+) — (.+?)\n"
            r"\*\*Estado:\*\*[^*\n]*?(\w[\w ]+?)\s{2}\n"
            r"\*\*Fecha:\*\*\s*(.+?)\s{2}\n"
            r"\*\*Respuesta del auditado:\*\*\s*(.*?)\s{2}\n"
            r"\*\*Hallazgo:\*\*\s*(.*?)\s{2}\n"
            r"\*\*Evidencia requerida:\*\*\s*(.*?)\s{2}\n"
            r"\*\*Brecha encontrada:\*\*\s*(.*?)\s{2}\n",
            re.DOTALL,
        )
        for m in block_pattern.finditer(content):
            control_id = m.group(1).strip()
            finding = Finding(
                control_id=control_id,
                title=m.group(2).strip(),
                estado=m.group(3).strip(),
                hallazgo=m.group(6).strip(),
                evidencia_requerida=m.group(7).strip(),
                brecha_encontrada=m.group(8).strip(),
                respuesta_usuario=m.group(5).strip(),
                fecha=m.group(4).strip(),
            )
            self.state.findings[control_id] = finding

        # Controles pendientes
        pending_section = re.search(
            r"## Controles Pendientes\n(.*?)(?=\n## |\Z)", content, re.DOTALL
        )
        if pending_section:
            pending_text = pending_section.group(1)
            self.state.pending_controls = re.findall(r"- \[ \] (A[\d.]+)", pending_text)
