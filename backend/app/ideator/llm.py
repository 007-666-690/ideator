"""Cliente del modelo de IA.

- AzureOpenAIClient: GPT-5 desplegado en Azure OpenAI (endpoint v1 compatible con OpenAI).
- GeminiClient: Gemini de Google AI Studio por su endpoint compatible con OpenAI (clave de API).
- VertexClient: Gemini en Vertex AI (Google Cloud), cobrado a la cuenta de facturación del proyecto,
  así que usa los créditos de educación. Se autentica con una cuenta de servicio (archivo JSON).
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


class VertexClient(AzureOpenAIClient):
    """Gemini en Vertex AI por su endpoint compatible con OpenAI.

    Vertex no acepta claves de API fijas: con la cuenta de servicio se firma un JWT (RS256) y se
    cambia por un token de acceso de Google que dura 1 hora; se renueva solo antes de vencer.
    """

    name = "vertex"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPE = "https://www.googleapis.com/auth/cloud-platform"

    def __init__(self, settings: Settings) -> None:
        import threading

        from ..cloud import metadata_project, on_cloud_run

        path = settings.vertex_key_path
        self._metadata = path is None and on_cloud_run()  # Cloud Run: identidad del servicio, sin archivo
        if self._metadata:
            self._lock = threading.Lock()
            self._token, self._expires_at = "", 0.0
            project = settings.vertex_project or metadata_project()
            self._init_endpoint(settings, project)
            return
        if path is None:
            raise LLMUnavailable(
                f"Falta el archivo de la cuenta de servicio de Vertex AI ({settings.vertex_credentials_file}). "
                "Descárgalo desde Google Cloud y guárdalo en la carpeta backend."
            )
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
            self._email = info["client_email"]
            self._private_key = info["private_key"]
            project = settings.vertex_project or info["project_id"]
        except (ValueError, KeyError) as exc:
            raise LLMUnavailable("El archivo de la cuenta de servicio de Vertex AI no es válido (se esperaba el JSON descargado de Google Cloud).") from exc
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0
        self._init_endpoint(settings, project)

    def _init_endpoint(self, settings: Settings, project: str) -> None:
        location = settings.vertex_location or "global"
        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        base_url = f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"
        self._setup(settings, base_url, "pendiente", self._model_id(settings.gemini_model))
        self.fallback_model = self._model_id(settings.gemini_fallback_model) if settings.gemini_fallback_model else ""

    @staticmethod
    def _model_id(model: str) -> str:
        return model if "/" in model else f"google/{model}"

    def _fetch_token(self) -> tuple[str, float]:
        if getattr(self, "_metadata", False):
            from ..cloud import metadata_token

            try:
                return metadata_token()
            except Exception as exc:  # noqa: BLE001
                raise LLMUnavailable("No se pudo obtener la identidad de Google Cloud para usar Vertex AI. Reintenta.") from exc
        import httpx
        import jwt

        now = int(time.time())
        assertion = jwt.encode(
            {"iss": self._email, "scope": self.SCOPE, "aud": self.TOKEN_URL, "iat": now, "exp": now + 3600},
            self._private_key,
            algorithm="RS256",
        )
        try:
            response = httpx.post(
                self.TOKEN_URL,
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise LLMUnavailable("No hay conexión con Google para autenticar Vertex AI. Reintenta.") from exc
        if response.status_code != 200:
            raise LLMUnavailable(
                "Google rechazó la cuenta de servicio de Vertex AI (revisa que el archivo JSON sea el actual y que la cuenta tenga el rol «Usuario de Vertex AI»)."
            )
        data = response.json()
        return data["access_token"], time.time() + int(data.get("expires_in", 3600))

    def _ensure_token(self) -> None:
        with self._lock:
            if self._token and time.time() < self._expires_at - 300:
                return
            self._token, self._expires_at = self._fetch_token()
            self._client.api_key = self._token

    def _request(self, system: str, user: str, schema: type[BaseModel], effort: str) -> tuple[str, Any]:
        self._ensure_token()
        return super()._request(system, user, schema, effort)


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
    elif settings.llm_provider == "vertex":
        _client = VertexClient(settings)
    else:
        raise LLMUnavailable(f"Proveedor de IA desconocido: {settings.llm_provider}")
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Permite inyectar un cliente (pruebas)."""
    global _client
    _client = client
