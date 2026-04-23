"""
knowledge_base.py — Base de conocimiento para documentos ISO 27001.

Responsabilidades:
  1. Cargar archivos .txt, .md y .pdf desde el directorio knowledge/.
  2. Fragmentar el contenido en secciones por control (A.x.y).
  3. Recuperar el fragmento exacto de un control cuando el motor lo solicite
     (inyección de contexto inteligente → evita enviar el documento completo).
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Excepciones
# ──────────────────────────────────────────────────────────────────────────────

class KnowledgeLoadError(Exception):
    """Error al cargar o parsear un archivo de conocimiento."""


# ──────────────────────────────────────────────────────────────────────────────
# Carga de archivos
# ──────────────────────────────────────────────────────────────────────────────

def _load_txt(path: Path) -> str:
    """Lee un archivo de texto plano o Markdown."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _load_pdf(path: Path) -> str:
    """
    Extrae texto de un PDF usando PyMuPDF (fitz) con fallback a pdfplumber.
    Ambas librerías están en requirements.txt.
    """
    # Intento 1: PyMuPDF (más rápido, mejor en PDFs con estructura)
    try:
        import fitz  # type: ignore  (PyMuPDF)
        doc = fitz.open(str(path))
        pages = [page.get_text("text") for page in doc]
        doc.close()
        text = "\n".join(pages)
        logger.info("PDF cargado con PyMuPDF: %s (%d páginas)", path.name, len(pages))
        return text
    except ImportError:
        logger.debug("PyMuPDF no disponible, intentando pdfplumber...")
    except Exception as exc:
        logger.warning("PyMuPDF falló en %s: %s", path.name, exc)

    # Intento 2: pdfplumber
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        text = "\n".join(pages)
        logger.info("PDF cargado con pdfplumber: %s (%d páginas)", path.name, len(pages))
        return text
    except ImportError as exc:
        raise KnowledgeLoadError(
            "No se encontró PyMuPDF ni pdfplumber. "
            "Ejecuta: pip install pymupdf pdfplumber"
        ) from exc
    except Exception as exc:
        raise KnowledgeLoadError(f"No se pudo leer el PDF {path.name}: {exc}") from exc


def load_document(path: Path) -> str:
    """Carga un documento de conocimiento según su extensión."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        content = _load_txt(path)
    elif suffix == ".pdf":
        content = _load_pdf(path)
    else:
        raise KnowledgeLoadError(
            f"Formato no soportado: {suffix}. Usa .txt, .md o .pdf"
        )
    logger.info("Documento cargado: %s (%d chars)", path.name, len(content))
    return content


# ──────────────────────────────────────────────────────────────────────────────
# Fragmentación por control
# ──────────────────────────────────────────────────────────────────────────────

# Patrón para detectar encabezados de controles del Anexo A
# Ejemplos: "A.5.1", "A.5.1.1", "Control A.8.2", "5.1 Políticas de SI"
_CONTROL_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:Control\s+|Annex\s+A[\s.]*|Anexo\s+A[\s.]*)??"
    r"(A\.?\d+(?:\.\d+){1,2})"
    r"[^\n]*",
    re.IGNORECASE,
)


def _fragment_by_controls(text: str) -> Dict[str, str]:
    """
    Divide el texto en un diccionario {control_id: fragmento_texto}.
    El fragmento incluye el encabezado y el texto hasta el siguiente control.

    Si el documento no tiene marcadores de control, se devuelve
    {"_full_": texto_completo} para que el motor use todo el contexto.
    """
    matches = list(_CONTROL_PATTERN.finditer(text))

    if not matches:
        logger.warning("No se encontraron marcadores de control (A.x.x) en el documento.")
        return {"_full_": text}

    fragments: Dict[str, str] = {}
    for i, match in enumerate(matches):
        control_id = match.group(1).upper().replace("A", "A", 1)  # normalizar
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        fragment = text[start:end].strip()
        # Truncar fragmentos muy largos
        if len(fragment) > Config.MAX_CONTEXT_CHARS:
            fragment = fragment[: Config.MAX_CONTEXT_CHARS] + "\n[...fragmento truncado...]"
        # Permitir múltiples secciones para el mismo control (tomar la primera)
        if control_id not in fragments:
            fragments[control_id] = fragment

    logger.info("Fragmentación completada: %d controles detectados.", len(fragments))
    return fragments


# ──────────────────────────────────────────────────────────────────────────────
# Clase principal
# ──────────────────────────────────────────────────────────────────────────────

class KnowledgeBase:
    """
    Almacena y consulta el conocimiento sobre ISO 27001 cargado desde archivos externos.
    """

    def __init__(self) -> None:
        # {control_id → texto_del_control}
        self._fragments: Dict[str, str] = {}
        # Texto completo de todos los documentos (para búsquedas genéricas)
        self._full_text: str = ""
        self._loaded_files: List[str] = []

    def load_directory(self, directory: Optional[Path] = None) -> int:
        """
        Carga todos los documentos del directorio knowledge/ (o el indicado).
        Retorna el número de archivos cargados.
        """
        directory = directory or Config.KNOWLEDGE_DIR
        supported = (".txt", ".md", ".pdf")
        files = [f for f in directory.iterdir() if f.suffix.lower() in supported]

        if not files:
            logger.warning(
                "No se encontraron documentos en %s. "
                "Coloca archivos .txt/.md/.pdf con los controles ISO.",
                directory,
            )
            return 0

        for file_path in files:
            try:
                content = load_document(file_path)
                self._full_text += f"\n\n{'='*60}\n# Documento: {file_path.name}\n{'='*60}\n{content}"
                fragments = _fragment_by_controls(content)
                self._fragments.update(fragments)
                self._loaded_files.append(file_path.name)
            except KnowledgeLoadError as exc:
                logger.error("Error cargando %s: %s", file_path.name, exc)

        logger.info(
            "Base de conocimiento lista: %d archivos, %d controles indexados.",
            len(self._loaded_files),
            len(self._fragments),
        )
        return len(self._loaded_files)

    def load_file(self, path: Path) -> None:
        """Carga un único archivo a la base de conocimiento."""
        content = load_document(path)
        self._full_text += f"\n\n{'='*60}\n# Documento: {path.name}\n{'='*60}\n{content}"
        fragments = _fragment_by_controls(content)
        self._fragments.update(fragments)
        self._loaded_files.append(path.name)
        logger.info("Archivo añadido a KB: %s", path.name)

    def get_context_for_control(self, control_id: str) -> str:
        """
        Recupera el fragmento de texto correspondiente a un control específico.
        Si no existe, busca coincidencias parciales (ej: "A.5" → devuelve todos los A.5.x).
        Si no hay nada, devuelve un mensaje indicando ausencia.
        """
        # Búsqueda exacta
        normalized = control_id.upper()
        if normalized in self._fragments:
            return self._fragments[normalized]

        # Búsqueda parcial (prefijo)
        partial_matches = {
            k: v for k, v in self._fragments.items() if k.startswith(normalized)
        }
        if partial_matches:
            combined = "\n\n".join(partial_matches.values())
            if len(combined) > Config.MAX_CONTEXT_CHARS:
                combined = combined[: Config.MAX_CONTEXT_CHARS] + "\n[...truncado...]"
            return combined

        # Fallback: primeros MAX_CONTEXT_CHARS del documento completo
        if self._full_text:
            logger.warning(
                "Control %s no encontrado en KB. Usando contexto general.", control_id
            )
            return self._full_text[: Config.MAX_CONTEXT_CHARS]

        return f"[Sin información disponible para el control {control_id}]"

    def get_all_control_ids(self) -> List[str]:
        """Retorna la lista de todos los controles indexados."""
        return sorted(k for k in self._fragments if k != "_full_")

    def get_summary(self) -> str:
        """Resumen del estado de la base de conocimiento."""
        if not self._loaded_files:
            return "⚠️  Base de conocimiento vacía. No se han cargado documentos ISO."
        controls = len([k for k in self._fragments if k != "_full_"])
        return (
            f"📚 Base de conocimiento: {len(self._loaded_files)} archivo(s) cargado(s) | "
            f"{controls} controles indexados\n"
            f"   Archivos: {', '.join(self._loaded_files)}"
        )

    @property
    def is_loaded(self) -> bool:
        return bool(self._loaded_files)
