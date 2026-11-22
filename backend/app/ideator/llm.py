"""Cliente del modelo de IA.

- AzureOpenAIClient: GPT-5 desplegado en Azure OpenAI (endpoint v1 compatible con OpenAI).
- GeminiClient: Gemini de Google por su endpoint compatible con OpenAI (créditos de Google Cloud).
- FakeLLM (en fake.py): respuestas deterministas para pruebas automáticas y modo demo.

Todas las respuestas se piden como salida estructurada (JSON Schema estricto) y se
validan con Pydantic. Si la respuesta no calza con el esquema se reintenta una vez
indicando el error al modelo.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..observability import LLM_LATENCY, LLM_REQUESTS, LLM_TOKENS

logger = logging.getLogger("ideator.llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Error al usar el modelo de IA (se traduce a 502/503 en la API)."""

    status = 502
    code = "llm_error"


class LLMUnavailable(LLMError):
    status = 503
    code = "llm_unavailable"


class LLMBadOutput(LLMError):
    status = 502
    code = "llm_bad_output"


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema compatible con el modo estricto de salidas estructuradas."""
    schema = model.model_json_schema()

    def fix(node: Any) -> None:
        if isinstance(node, list):
            for value in node:
                fix(value)
            return
        if not isinstance(node, dict):
            return
        if "$ref" in node and len(node) > 1:
            ref = node["$ref"]
            node.clear()
            node["$ref"] = ref
            return
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            if "properties" in node:
                node["required"] = list(node["properties"].keys())
        node.pop("default", None)
        for key, value in node.items():
            # En properties/$defs las claves son nombres (p. ej. una columna llamada "default"), no palabras clave.
            if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
                for sub in value.values():
                    fix(sub)
            elif key in ("items", "anyOf", "allOf", "oneOf", "prefixItems"):
                fix(value)

    fix(schema)
    return schema


def extract_json(text: str) -> str:
    """Saca el primer objeto JSON de un texto (por si el modelo agrega texto alrededor)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return text
    return text[start : end + 1]


class LLMClient(ABC):
    name = "base"

    @abstractmethod
    def complete(self, *, task: str, system: str, user: str, schema: type[T], effort: str | None = None) -> T:
        """Devuelve una instancia validada de `schema`."""


class AzureOpenAIClient(LLMClient):
    name = "azure"

    def __init__(self, settings: Settings) -> None:
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise LLMUnavailable("El modelo de IA no está configurado (AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY).")
        self._setup(settings, settings.azure_openai_endpoint.rstrip("/"), settings.azure_openai_api_key, settings.azure_openai_deployment)

    def _setup(self, settings: Settings, base_url: str, api_key: str, model: str) -> None:
        from openai import OpenAI

        self.model = model
        self.default_effort = settings.llm_reasoning_effort
        self.max_tokens = settings.llm_max_output_tokens
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=settings.llm_timeout_seconds, max_retries=2)
        self._strict_supported = True
        self._tokens_param = "max_completion_tokens"
        self.fallback_model = ""

    def _request(self, system: str, user: str, schema: type[BaseModel], effort: str) -> tuple[str, Any]:
        import openai

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            self._tokens_param: self.max_tokens,
            "reasoning_effort": effort,
        }
        if self._strict_supported:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": strict_json_schema(schema), "strict": True},
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}
            messages[0]["content"] = (
                system
                + "\n\nResponde SOLO con un objeto JSON válido que cumpla exactamente este JSON Schema:\n"
                + json.dumps(strict_json_schema(schema), ensure_ascii=False)
            )
        try:
            response = self._client.chat.completions.create(**kwargs)
        except (openai.RateLimitError, openai.InternalServerError) as exc:
            # Modelo saturado: se prueba una vez con el modelo de respaldo, si hay uno.
            if not self.fallback_model or self.fallback_model == kwargs["model"]:
                raise
            logger.warning("Modelo saturado, se usa el de respaldo", extra={"model": kwargs["model"], "fallback": self.fallback_model, "error": str(exc)[:200]})
            kwargs["model"] = self.fallback_model
            response = self._client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            text = str(exc).lower()
            if self._strict_supported and ("response_format" in text or "json_schema" in text or "schema" in text):
                logger.warning("El endpoint no acepta json_schema estricto; se usa json_object", extra={"error": str(exc)[:300]})
                self._strict_supported = False
                return self._request(system, user, schema, effort)
            if "max_completion_tokens" in text and self._tokens_param == "max_completion_tokens":
                self._tokens_param = "max_tokens"
                return self._request(system, user, schema, effort)
            if "reasoning_effort" in text and "reasoning_effort" in kwargs:
                kwargs.pop("reasoning_effort")
                response = self._client.chat.completions.create(**kwargs)
            else:
                raise
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMBadOutput("La respuesta del modelo quedó incompleta (límite de tokens). Intenta de nuevo.")
        refusal = getattr(choice.message, "refusal", None)
        if refusal:
            raise LLMBadOutput(f"El modelo se negó a responder: {refusal}")
        return choice.message.content or "", response.usage

    def complete(self, *, task: str, system: str, user: str, schema: type[T], effort: str | None = None) -> T:
        import openai

        effort = effort or self.default_effort
        start = time.perf_counter()
        outcome = "error"
        try:
            content, usage = self._request(system, user, schema, effort)
            self._count_tokens(task, usage)
            try:
                result = schema.model_validate_json(extract_json(content))
            except ValidationError as exc:
                logger.warning("Salida inválida, se reintenta", extra={"task": task, "errors": str(exc)[:500]})
                retry_user = (
                    user
                    + "\n\nTu respuesta anterior no cumplió el esquema. Errores:\n"
                    + str(exc)[:2000]
                    + "\nDevuelve el JSON completo y corregido."
                )
                content, usage = self._request(system, retry_user, schema, effort)
                self._count_tokens(task, usage)
                try:
                    result = schema.model_validate_json(extract_json(content))
                except ValidationError as exc2:
                    raise LLMBadOutput("La IA devolvió una respuesta con formato inválido. Intenta de nuevo.") from exc2
            outcome = "ok"
            return result
        except openai.APITimeoutError as exc:
            raise LLMUnavailable("La IA tardó demasiado en responder (tiempo agotado). Lo que ya tenías sigue guardado: reintenta.") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailable("No hay conexión con el proveedor de IA (red o servicio caído). Lo que ya tenías sigue guardado: reintenta.") from exc
        except openai.RateLimitError as exc:
            raise LLMUnavailable("Se alcanzó el límite de uso de la IA (429): demasiadas consultas por minuto o se acabaron los créditos. Espera un momento y reintenta.") from exc
        except openai.AuthenticationError as exc:
            raise LLMUnavailable("Las credenciales del modelo de IA no son válidas (clave de API incorrecta o revocada). Revisa backend/.env.") from exc
        except openai.APIStatusError as exc:
            raise LLMUnavailable(f"El proveedor de IA respondió con error {exc.status_code}" + (" (servicio saturado o caído)" if exc.status_code >= 500 else "") + ". Lo que ya tenías sigue guardado: reintenta.") from exc
        finally:
            elapsed = time.perf_counter() - start
            LLM_REQUESTS.labels(task, outcome).inc()
            LLM_LATENCY.labels(task).observe(elapsed)
            logger.info("Llamada al modelo", extra={"task": task, "outcome": outcome, "seconds": round(elapsed, 2), "effort": effort})

    @staticmethod
    def _count_tokens(task: str, usage: Any) -> None:
        if not usage:
            return
        LLM_TOKENS.labels(task, "input").inc(getattr(usage, "prompt_tokens", 0) or 0)
        LLM_TOKENS.labels(task, "output").inc(getattr(usage, "completion_tokens", 0) or 0)


class GeminiClient(AzureOpenAIClient):
    """Gemini por su API compatible con OpenAI: mismas instrucciones, esquemas y reintentos."""

    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise LLMUnavailable("El modelo de IA no está configurado (GEMINI_API_KEY).")
        self._setup(settings, settings.gemini_base_url, settings.gemini_api_key, settings.gemini_model)
        self.fallback_model = settings.gemini_fallback_model


_client: LLMClient | None = None


def get_llm(settings: Settings) -> LLMClient:
    global _client
    if _client is not None:
        return _client
    if settings.llm_provider == "fake":
        from .fake import FakeLLM

        _client = FakeLLM()
    elif settings.llm_provider == "azure":
        _client = AzureOpenAIClient(settings)
    elif settings.llm_provider == "gemini":
        _client = GeminiClient(settings)
    else:
        raise LLMUnavailable(f"Proveedor de IA desconocido: {settings.llm_provider}")
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Permite inyectar un cliente (pruebas)."""
    global _client
    _client = client
