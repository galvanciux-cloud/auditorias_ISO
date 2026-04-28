# 🔒 Agente IA — Auditoría ISO 27001:2022

Asistente de auditoría interactivo por consola que guía el proceso de evaluación
de cumplimiento de la norma ISO 27001:2022 usando IA (Gemini u Ollama).


<img width="1286" height="774" alt="iso1" src="https://github.com/user-attachments/assets/03e2e096-40d9-4bfc-9693-d112b1266789" />
<img width="1283" height="483" alt="2iso" src="https://github.com/user-attachments/assets/c154e1b7-58d6-4892-b4f7-05dce0781598" />
<img width="1314" height="766" alt="iso3" src="https://github.com/user-attachments/assets/cb9c33fa-f13f-4985-84a1-1153c02d6e09" />
<img width="1283" height="483" alt="2iso" src="https://github.com/user-attachments/assets/c154e1b7-58d6-4892-b4f7-05dce0781598" />



---

## 📁 Árbol de Archivos

```
iso27001_agent/
│
├── main.py                  # CLI principal (Typer) — punto de entrada
├── config.py                # Variables de entorno y configuración central
├── llm_router.py            # Abstracción multi-modelo (Gemini / Ollama)
├── knowledge_base.py        # Carga y fragmentación de documentos ISO
├── memory_manager.py        # Persistencia del estado en estado_auditoria.md
├── audit_engine.py          # Motor de auditoría: prompts, evaluación, flujo
├── report_generator.py      # Generación de informes TXT y PDF
│
├── requirements.txt         # Dependencias del proyecto
├── .env.example             # Plantilla de variables de entorno
├── .env                     # (crear manualmente, no subir a git)
│
├── knowledge/               # 📂 Coloca aquí tus documentos ISO
│   ├── iso27001_anexo_a.pdf
│   └── politica_seguridad.md
│
├── reports/                 # 📂 Informes generados automáticamente
│   ├── informe_iso27001_20241201_143022.txt
│   └── informe_iso27001_20241201_143022.pdf
│
├── estado_auditoria.md      # Estado persistente (generado automáticamente)
└── agent.log                # Log de interacciones (generado automáticamente)
```

---

## ⚙️ Instalación y Configuración del Entorno

### 1. Clonar el repositorio y crear el entorno virtual

```bash
# Clonar / navegar al directorio
cd iso27001_agent

# Crear entorno virtual (Python 3.10+)
python -m venv .venv

# Activar entorno virtual
# Linux / macOS:
source .venv/bin/activate
# Windows CMD:
.venv\Scripts\activate.bat
# Windows PowerShell:
.venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
# Copiar la plantilla
cp .env.example .env

# Editar con tu editor preferido
nano .env   # o: code .env / vim .env
```

#### Opción A — Usar Ollama (local, gratuito)

```bash
# Asegúrate de tener Ollama instalado: https://ollama.ai
ollama pull llama3          # o: mistral, llama3.1, gemma2, etc.
ollama serve                # Inicia el servidor (si no corre ya como servicio)
```

En `.env`:
```ini
LLM_BACKEND=ollama
OLLAMA_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434
```

#### Opción B — Usar Google Gemini (API en la nube)

Obtén tu API Key en: https://aistudio.google.com/app/apikey

En `.env`:
```ini
LLM_BACKEND=gemini
GEMINI_API_KEY=AIza...tu_clave_aqui
GEMINI_MODEL=gemini-1.5-flash
```

---

## 📚 Cómo Adjuntar un PDF de ISO 27001

El agente usa tus documentos para **inyectar el texto exacto de cada control**
en el prompt de evaluación (evita alucinaciones y ahorra tokens).

### Método 1: Comando `load-doc` (recomendado)

```bash
# Cargar el Anexo A de ISO 27001
python main.py load-doc /ruta/a/iso27001_anexo_a.pdf

# Cargar política interna de seguridad
python main.py load-doc /ruta/a/politica_sgsi.pdf

# El documento se copia automáticamente a knowledge/ para uso futuro
```

### Método 2: Copiar manualmente al directorio knowledge/

```bash
cp /ruta/a/iso27001.pdf ./knowledge/
```

El agente carga todos los archivos de `knowledge/` al iniciar.

### Formatos soportados

| Formato | Soporte | Notas |
|---------|---------|-------|
| `.pdf`  | ✅ Completo | Requiere PyMuPDF (instalado automáticamente) |
| `.md`   | ✅ Completo | Recomendado para documentos propios |
| `.txt`  | ✅ Completo | Texto plano sin formato |

---

## 🚀 Iniciar una Auditoría

### Auditoría completa (todos los controles del Anexo A)

```bash
python main.py start
```

El agente preguntará:
1. ¿Reanudar auditoría existente o iniciar nueva?
2. Nombre de la organización
3. Nombre del auditor
4. Alcance de la auditoría

Luego comenzará control por control, formulando preguntas específicas.

### Auditoría parcial (controles específicos)

```bash
# Auditar solo controles de acceso y criptografía
python main.py start --controls A.5.15,A.5.16,A.5.17,A.5.18,A.8.24

# Auditar todos los controles tecnológicos (A.8.x)
python main.py start --controls A.8.1,A.8.2,A.8.3,A.8.7,A.8.8,A.8.13,A.8.15
```

### Pausar y reanudar

Pulsa `Ctrl+C` en cualquier momento. El progreso se guarda automáticamente
en `estado_auditoria.md`. Al volver a ejecutar `start`, el agente ofrecerá
retomar desde donde lo dejaste.

---

## 📊 Consultar el Estado de la Auditoría

```bash
python main.py status
```

Muestra una tabla con:
- Controles conformes / no conformes / observaciones
- Tasa de conformidad (%)
- Lista de no conformidades detectadas

---

## 📄 Generar Informes

```bash
# Generar TXT y PDF (por defecto)
python main.py report

# Solo PDF
python main.py report --format pdf

# Solo TXT
python main.py report --format txt

# Con ruta personalizada
python main.py report --output /ruta/informe_empresa_2024
```

Los informes se guardan en el directorio `reports/`.

---

## 📋 Listar Todos los Controles

```bash
python main.py list-controls
```

Muestra la tabla completa de los 93 controles del Anexo A de ISO 27001:2022.

---

## 🗑️ Reiniciar la Auditoría

```bash
python main.py reset --yes
```

⚠️ Borra `estado_auditoria.md`. Los informes ya generados NO se borran.

---

## 🔍 Flujo de Evaluación (Cómo Funciona por Dentro)

```
┌─────────────────────────────────────────────────────────┐
│  Para cada control A.x.y:                               │
│                                                         │
│  1. KB busca el fragmento exacto del control en los     │
│     documentos cargados (no todo el PDF)                │
│                                                         │
│  2. La IA genera una pregunta de auditoría específica   │
│     basada en el texto del control                      │
│                                                         │
│  3. El auditor escribe la respuesta del auditado        │
│                                                         │
│  4. La IA evalúa con este prompt:                       │
│     [System: rol de Lead Auditor ISO 27001]             │
│     [Texto del control ISO] + [Respuesta del auditado]  │
│     → Responde SOLO con JSON estructurado               │
│                                                         │
│  5. JSON parseado: {estado, hallazgo,                   │
│     evidencia_requerida, brecha_encontrada,             │
│     pregunta_followup, nivel_riesgo}                    │
│                                                         │
│  6. Si hay followup → máximo 2 rondas adicionales       │
│                                                         │
│  7. Finding guardado en estado_auditoria.md             │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ Resolución de Problemas

| Error | Solución |
|-------|----------|
| `No se pudo conectar con Ollama` | Ejecuta `ollama serve` en otra terminal |
| `GEMINI_API_KEY no configurada` | Añade la clave en `.env` |
| `No se encontraron documentos ISO` | Coloca archivos en `knowledge/` o usa `load-doc` |
| `JSON inválido en evaluación` | Prueba con un modelo más grande o ajusta temperatura en `llm_router.py` |
| `PDF sin texto extraíble` | El PDF puede ser escaneado; usa una versión nativa o aplica OCR previo |

---

## 📝 Notas Técnicas

- **Temperatura de IA**: 0.2 (configurada en `llm_router.py`) para maximizar precisión
- **Contexto por control**: máximo 4000 chars (configurable con `MAX_CONTEXT_CHARS` en `.env`)
- **Preguntas de seguimiento**: máximo 2 rondas por control
- **Logging**: todas las interacciones se registran en `agent.log` para auditoría del sistema
- **Seguridad del .env**: añade `.env` a tu `.gitignore` para no exponer API keys

---

## 📖 Referencia de Comandos

```
python main.py --help              # Ayuda general
python main.py start --help        # Opciones de start
python main.py start               # Iniciar/reanudar auditoría completa
python main.py start -c A.5.1,A.8.1  # Auditoría parcial
python main.py status              # Ver progreso
python main.py report              # Generar informes
python main.py report --format pdf # Solo PDF
python main.py load-doc <archivo>  # Cargar documento ISO
python main.py list-controls       # Listar controles Anexo A
python main.py reset --yes         # Reiniciar auditoría
```
