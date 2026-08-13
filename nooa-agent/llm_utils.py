"""
Helper para llamadas LLM con retry, timeout, backoff y rate limit handling.

Filosofía NOOA: un solo punto de entrada para todas las llamadas a LiteLLM.

Pass-by-reference: tool results se pasan como bounded previews,
no como JSON serializado completo. Esto reduce tokens ~50%.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from litellm import completion

from config import MODEL

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60  # segundos
DEFAULT_BACKOFF = 2.0  # factor de backoff exponencial

# Regex para detectar rate limit y extraer tiempo de espera
_RATE_LIMIT_RE = re.compile(r"Please try again in ([\d.]+)s", re.IGNORECASE)


def _extract_rate_limit_wait(error: Exception) -> float | None:
    """Extrae el tiempo de espera del mensaje de rate limit de Groq."""
    msg = str(error)
    match = _RATE_LIMIT_RE.search(msg)
    if match:
        return float(match.group(1))
    return None


def llm_call(
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1500,
    model: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """
    Llama al LLM con retry exponencial, timeout y rate limit handling.

    Si el error es de rate limit, espera el tiempo que indica el mensaje
    en vez de usar backoff exponencial genérico.

    Args:
        messages: lista de mensajes en formato OpenAI
        tools: tools schema opcional para tool calling
        temperature: temperatura del modelo
        max_tokens: máximo de tokens en la respuesta
        model: modelo a usar (default: config.MODEL)
        max_retries: número máximo de reintentos
        timeout: timeout en segundos

    Returns:
        Respuesta del modelo (Message)

    Raises:
        RuntimeError: si todos los reintentos fallan
    """
    selected_model = model or MODEL
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                "LLM call attempt %d/%d — model=%s, tools=%s, temp=%.2f, max_tokens=%d",
                attempt, max_retries, selected_model,
                len(tools) if tools else 0, temperature, max_tokens,
            )

            kwargs: dict[str, Any] = {
                "model": selected_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
            if tools:
                kwargs["tools"] = tools

            response = completion(**kwargs)
            logger.debug("LLM call succeeded on attempt %d", attempt)
            return response

        except Exception as e:
            last_error = e
            logger.warning(
                "LLM call attempt %d/%d failed: %s",
                attempt, max_retries, e,
            )
            if attempt < max_retries:
                # Si es rate limit, esperar el tiempo que indica el mensaje
                rate_limit_wait = _extract_rate_limit_wait(e)
                if rate_limit_wait is not None:
                    wait = min(rate_limit_wait + 2.0, 120.0)  # cap a 2 min
                    logger.info("Rate limit detected — waiting %.1fs (server suggested %.1fs)", wait, rate_limit_wait)
                else:
                    wait = DEFAULT_BACKOFF ** attempt
                    logger.info("Retrying in %.1fs...", wait)
                time.sleep(wait)

    logger.error("LLM call failed after %d attempts: %s", max_retries, last_error)
    raise RuntimeError(
        f"LLM call failed after {max_retries} attempts. "
        f"Last error: {last_error}"
    )
