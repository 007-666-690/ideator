"""Configuración de la aplicación.

Todo se lee desde variables de entorno (o un archivo .env en desarrollo).
Si se define AZURE_KEY_VAULT_URL, los secretos se cargan desde Azure Key Vault
y reemplazan a los valores de las variables de entorno.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("ideator.config")

DEFAULT_SECRET = "dev-secret-change-me-dev-secret-change-me"

# Nombre del secreto en Key Vault -> atributo de Settings
KEY_VAULT_SECRETS = {
    "ideator-secret-key": "secret_key",
    "ideator-database-url": "database_url",
    "azure-openai-api-key": "azure_openai_api_key",
    "gemini-api-key": "gemini_api_key",
    "microsoft-client-secret": "microsoft_client_secret",
    "google-client-secret": "google_client_secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Ideator"
    environment: str = "development"  # development | test | production
    log_level: str = "INFO"

    database_url: str = "sqlite:///./ideator.db"

    # Sesiones (JWT en cookie HttpOnly)
    secret_key: str = DEFAULT_SECRET
    access_token_minutes: int = 480
    cookie_secure: bool = False
    session_cookie_name: str = "ideator_session"

    # URLs
    frontend_url: str = "http://localhost:5173"
    backend_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173"

    # IA
    llm_provider: str = "fake"  # azure | gemini | fake
    azure_openai_endpoint: str = ""  # https://<recurso>.openai.azure.com/openai/v1
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-5"
    # Gemini (Google AI Studio / créditos de Google Cloud), por su API compatible con OpenAI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_reasoning_effort: str = "low"  # minimal | low | medium | high
    llm_timeout_seconds: int = 300
    llm_max_output_tokens: int = 32000

    # SSO (OpenID Connect)
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "organizations"
    google_client_id: str = ""
    google_client_secret: str = ""

    # Carpeta con el frontend compilado (opcional): si se define, la API también sirve la SPA
    frontend_dist: str = ""

    # Azure Key Vault (opcional)
    azure_key_vault_url: str = ""

    # Límite de intentos de login por correo e IP
    login_max_attempts: int = 10
    login_window_seconds: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "fake":
            return True
        if self.llm_provider == "gemini":
            return bool(self.gemini_api_key)
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)


def _load_key_vault(settings: Settings) -> None:
    """Sobrescribe secretos con los valores de Azure Key Vault."""
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.keyvault.secrets import SecretClient  # type: ignore
    except ImportError:  # pragma: no cover - dependencia opcional
        logger.error("AZURE_KEY_VAULT_URL definido pero faltan azure-identity/azure-keyvault-secrets")
        raise

    client = SecretClient(vault_url=settings.azure_key_vault_url, credential=DefaultAzureCredential())
    for secret_name, attr in KEY_VAULT_SECRETS.items():
        try:
            value = client.get_secret(secret_name).value
        except Exception:  # noqa: BLE001 - un secreto ausente no es fatal
            logger.warning("Secreto %s no encontrado en Key Vault", secret_name)
            continue
        if value:
            setattr(settings, attr, value)
    logger.info("Secretos cargados desde Azure Key Vault")


def validate_settings(settings: Settings) -> None:
    if settings.is_production:
        if settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32:
            raise RuntimeError("SECRET_KEY debe definirse (mínimo 32 caracteres) en producción")
        if settings.llm_provider == "fake":
            raise RuntimeError("En producción LLM_PROVIDER debe ser 'azure' o 'gemini'")
        if not settings.cookie_secure:
            raise RuntimeError("En producción COOKIE_SECURE debe ser true")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.azure_key_vault_url:
        _load_key_vault(settings)
    validate_settings(settings)
    return settings
