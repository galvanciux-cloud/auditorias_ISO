"""
llm_router.py — Capa de abstracción para los backends de IA.

Soporta:
  - Google Gemini  (via google-generativeai)
  - Ollama         (via HTTP local o librería ollama)

El resto del sistema siempre llama a `LLMRouter.generate(prompt)` sin importar
qué backend esté activo.
"""

import json
import logging
import time
from typing import Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Excepciones personalizadas
# ──────────────────────────────────────────────────────────────────────────────

class LLMConnectionError(Exception):
    """No se pudo conectar con el backend de IA (Ollama caído, red, etc.)."""


class LLMAPIError(Exception):
    """La API devolvió un error (clave inválida, cuota superada, modelo no existe...)."""


class LLMParseError(Exception):
    """La respuesta del modelo no pudo ser parseada como JSON cuando se esperaba."""


# ──────────────────────────────────────────────────────────────────────────────
# Backend Ollama
# ──────────────────────────────────────────────────────────────────────────────

class OllamaBackend:
    """Wrapper para la API REST de Ollama (http://localhost:11434)."""

    def __init__(self) -> None:
        self.base_url = Config.OLLAMA_BASE_URL.rstrip("/")
        self.model = Config.OLLAMA_MODEL
        self.timeout = Config.OLLAMA_TIMEOUT

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Llama al endpoint /api/generate de Ollama.
        Usa stream=False para recibir la respuesta completa de una vez.
        """
        url = f"{self.base_url}/api/generate"
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,   # Baja temperatura para respuestas más precisas
                "num_predict": 2048,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        logger.debug("Ollama → POST %s | model=%s | prompt_chars=%d",
                     url, self.model, len(prompt))
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(
                f"No se pudo conectar con Ollama en {self.base_url}. "
                "¿Está el servidor corriendo? (`ollama serve`)"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise LLMConnectionError(
                f"Ollama tardó más de {self.timeout}s en responder. "
                "Prueba con un modelo más pequeño o aumenta OLLAMA_TIMEOUT."
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise LLMAPIError(
                f"Ollama devolvió HTTP {resp.status_code}: {resp.text[:300]}"
            ) from exc

        data = resp.json()
        response_text = data.get("response", "").strip()
        logger.debug("Ollama ← %d chars | done=%s", len(response_text), data.get("done"))
        return response_text

    def health_check(self) -> bool:
        """Comprueba que Ollama está activo."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# Backend Gemini
# ──────────────────────────────────────────────────────────────────────────────

class GeminiBackend:
    """Wrapper para la API de Google Gemini."""

    def __init__(self) -> None:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise LLMAPIError(
                "Librería 'google-generativeai' no instalada. "
                "Ejecuta: pip install google-generativeai"
            ) from exc

        if not Config.GEMINI_API_KEY:
            raise LLMAPIError("GEMINI_API_KEY no configurada en .env")

        genai.configure(api_key=Config.GEMINI_API_KEY)
        self._genai = genai
        self.model_name = Config.GEMINI_MODEL
        logger.info("GeminiBackend inicializado con modelo: %s", self.model_name)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Genera texto usando la API de Gemini."""
        try:
            generation_config = self._genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=2048,
            )
            # En Gemini, el system prompt se incluye como primer mensaje del historial
            model = self._genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
                system_instruction=system_prompt or "",
            )
            logger.debug("Gemini → model=%s | prompt_chars=%d", self.model_name, len(prompt))
            response = model.generate_content(prompt)
            text = response.text.strip()
            logger.debug("Gemini ← %d chars", len(text))
            return text
        except Exception as exc:
            # La API de Gemini lanza google.api_core.exceptions en caso de error
            error_msg = str(exc)
            if "API_KEY" in error_msg.upper() or "INVALID_ARGUMENT" in error_msg.upper():
                raise LLMAPIError(f"Error de autenticación Gemini: {error_msg}") from exc
            if "QUOTA" in error_msg.upper() or "RATE" in error_msg.upper():
                raise LLMAPIError(f"Cuota de Gemini superada: {error_msg}") from exc
            raise LLMAPIError(f"Error inesperado en Gemini: {error_msg}") from exc


# ──────────────────────────────────────────────────────────────────────────────
# Router principal
# ──────────────────────────────────────────────────────────────────────────────

class LLMRouter:
    """
    Punto de entrada único para todos los módulos que necesiten IA.
    Decide qué backend usar según Config.LLM_BACKEND.
    """

    def __init__(self) -> None:
        backend = Config.LLM_BACKEND
        if backend == "ollama":
            self._backend = OllamaBackend()
            logger.info("LLMRouter: usando backend Ollama (%s)", Config.OLLAMA_MODEL)
        elif backend == "gemini":
            self._backend = GeminiBackend()
            logger.info("LLMRouter: usando backend Gemini (%s)", Config.GEMINI_MODEL)
        else:
            raise ValueError(f"Backend desconocido: {backend}")

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Genera una respuesta de texto. Reintenta una vez ante fallos transitorios."""
        for attempt in (1, 2):
            try:
                return self._backend.generate(prompt, system_prompt=system_prompt)
            except LLMConnectionError:
                if attempt == 2:
                    raise
                logger.warning("Fallo de conexión. Reintentando en 3s...")
                time.sleep(3)
        return ""  # nunca se alcanza, pero satisface al type checker

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        """
        Genera una respuesta y la parsea como JSON.
        Si el modelo devuelve markdown (```json ... ```), lo limpia antes de parsear.
        """
        raw = self.generate(prompt, system_prompt=system_prompt)
        # Limpiar bloques de código markdown si existen
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Quitar primera línea (```json o ```) y última (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("No se pudo parsear JSON. Raw response:\n%s", raw[:500])
            raise LLMParseError(
                f"La IA no devolvió JSON válido. Respuesta cruda:\n{raw[:300]}"
            ) from exc
