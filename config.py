"""
config.py — Gestión de configuración y variables de entorno.
Lee el archivo .env y expone una configuración centralizada para todos los módulos.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde el directorio raíz del proyecto
load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Clase de configuración central. Todas las constantes del proyecto vienen de aquí."""

    # ── Backend de IA ──────────────────────────────────────────────
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama").lower()  # "gemini" | "ollama"

    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))

    # ── Archivos del sistema ───────────────────────────────────────
    STATE_FILE: Path = Path(os.getenv("STATE_FILE", "estado_auditoria.md"))
    LOG_FILE: Path = Path(os.getenv("LOG_FILE", "agent.log"))
    KNOWLEDGE_DIR: Path = Path(os.getenv("KNOWLEDGE_DIR", "knowledge"))

    # ── Auditoría ─────────────────────────────────────────────────
    ORGANIZATION_NAME: str = os.getenv("ORGANIZATION_NAME", "Organización Auditada")
    AUDITOR_NAME: str = os.getenv("AUDITOR_NAME", "Auditor")
    MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))  # tokens aprox.

    # ── Informes ──────────────────────────────────────────────────
    REPORTS_DIR: Path = Path(os.getenv("REPORTS_DIR", "reports"))

    @classmethod
    def validate(cls) -> None:
        """Valida que la configuración mínima esté presente según el backend elegido."""
        if cls.LLM_BACKEND == "gemini" and not cls.GEMINI_API_KEY:
            raise ValueError(
                "LLM_BACKEND=gemini pero GEMINI_API_KEY está vacío. "
                "Revisa tu archivo .env"
            )
        if cls.LLM_BACKEND not in ("gemini", "ollama"):
            raise ValueError(
                f"LLM_BACKEND='{cls.LLM_BACKEND}' no es válido. Usa 'gemini' u 'ollama'."
            )
        # Crear directorios necesarios
        cls.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Configuración validada. Backend: %s", cls.LLM_BACKEND)


def setup_logging() -> None:
    """Configura el sistema de logging con salida a archivo y consola."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=[
            logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),  # también en consola (nivel WARNING+)
        ],
    )
    # Reducir verbosidad de librerías externas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
