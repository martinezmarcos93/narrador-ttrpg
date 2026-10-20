"""
LLM Client — wrapper para Ollama local.
Maneja streaming y llamadas síncronas, gestión de modelos.
"""

import json
from typing import Callable

import requests

from narrator.logger import logger

OLLAMA_DEFAULT_URL = "http://localhost:11434"


class LLMClient:
    def __init__(self, base_url: str = OLLAMA_DEFAULT_URL, model: str = "llama3.2"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = 0.85
        self.top_p = 0.9
        self.timeout = 120

    # ── Model management ──────────────────────────────────────
    def get_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception as e:
            logger.error(f"Error inesperado: {e}", exc_info=True)
        return []

    def is_connected(self) -> bool:
        return bool(self.get_models())

    # ── Sync call ─────────────────────────────────────────────
    def chat(self, messages: list[dict], max_tokens: int = 300) -> str:
        """Non-streaming call. Returns full response text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": max_tokens,
            },
        }
        try:
            r = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            return r.json().get("message", {}).get("content", "")
        except Exception as e:
            logger.error("Fallo en llamada síncrona al LLM: %s", e, exc_info=True)
            return f"[Error LLM: {e}]"

    # ── Streaming call ────────────────────────────────────────
    def stream_chat(
        self,
        messages: list[dict],
        on_chunk: Callable[[str], None],
        on_done: Callable[[str], None],
        max_tokens: int = 600,
    ):
        """
        Streaming call. Invoca on_chunk por cada token recibido
        y on_done con el texto completo al terminar.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": max_tokens,
            },
        }
        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self.timeout,
            ) as resp:
                if resp.status_code != 200:
                    # p.ej. 404 si el modelo no existe en Ollama
                    try:
                        err = resp.json().get("error", resp.text[:200])
                    except ValueError:
                        err = resp.text[:200]
                    on_done(f"[Error LLM ({resp.status_code}): {err}]")
                    return
                full = ""
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"Línea de stream no parseable: {e}")
                        continue
                    if data.get("error"):
                        on_done(f"[Error LLM: {data['error']}]")
                        return
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full += chunk
                        on_chunk(chunk)
                    if data.get("done"):
                        break
                on_done(full)
        except Exception as e:
            on_done(f"[Error de conexión: {e}]")
