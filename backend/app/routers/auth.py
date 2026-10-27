"""Autenticación: correo y contraseña + Single Sign-On (OpenID Connect)."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import SessionLocal, get_db
from ..deps import get_current_user
from ..errors import ApiError
from ..ideator.engine import log_activity
from ..models import SsoIdentity, User, utcnow
from ..security import (
    clear_session_cookie,
    create_access_token,
    hash_password,
    login_throttle,
    set_session_cookie,
    verify_password,
)

logger = logging.getLogger("ideator.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

PROVIDERS = {
    "microsoft": "Microsoft (Entra ID)",
    "google": "Google",
}
_MS_ISSUER = re.compile(r"^https://login\.microsoftonline\.com/([0-9a-fA-F-]{36})/v2\.0$")


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    has_password: bool
    sso_providers: list[str]


def user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        has_password=bool(user.password_hash),
        sso_providers=sorted({i.provider for i in user.identities}),
    )


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> UserOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ApiError(409, "email_in_use", "Ya existe una cuenta con ese correo.")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), last_login_at=utcnow())
    db.add(user)
    db.flush()
    log_activity(db, None, user, "user.registered")
    db.commit()
    set_session_cookie(response, create_access_token(user.id, settings), settings)
    return user_out(user)


@router.post("/login", response_model=UserOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    email = body.email.lower()
    client_ip = request.client.host if request.client else "?"
    key = f"{email}|{client_ip}"
    login_throttle.check(key, settings.login_max_attempts, settings.login_window_seconds)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, body.password):
        login_throttle.fail(key, settings.login_window_seconds)
        raise ApiError(401, "invalid_credentials", "Correo o contraseña incorrectos.")
    login_throttle.reset(key)
    user.last_login_at = utcnow()
    db.commit()
    set_session_cookie(response, create_access_token(user.id, settings), settings)
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(settings: Settings = Depends(get_settings)) -> Response:
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return user_out(user)


# ---------------------------------------------------------------------------
# SSO
# ---------------------------------------------------------------------------


def _provider_config(provider: str, settings: Settings) -> dict[str, Any] | None:
    if provider == "microsoft" and settings.microsoft_client_id and settings.microsoft_client_secret:
        return {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "server_metadata_url": f"https://login.microsoftonline.com/{settings.microsoft_tenant}/v2.0/.well-known/openid-configuration",
        }
    if provider == "google" and settings.google_client_id and settings.google_client_secret:
        return {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }
    return None


_oauth_clients: dict[str, Any] = {}


def get_oauth_client(provider: str, settings: Settings) -> Any:
    if provider not in PROVIDERS:
        raise ApiError(404, "unknown_provider", "Proveedor de SSO desconocido.")
    config = _provider_config(provider, settings)
    if config is None:
        raise ApiError(503, "sso_not_configured", f"El inicio de sesión con {PROVIDERS[provider]} no está configurado.")
    if provider not in _oauth_clients:
        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        oauth.register(
            name=provider,
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
            **config,
        )
        _oauth_clients[provider] = oauth.create_client(provider)
    return _oauth_clients[provider]


@router.get("/providers")
def providers(settings: Settings = Depends(get_settings)) -> list[dict[str, Any]]:
    return [{"id": p, "name": name, "enabled": _provider_config(p, settings) is not None} for p, name in PROVIDERS.items()]


@router.get("/sso/{provider}/login")
async def sso_login(provider: str, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    client = get_oauth_client(provider, settings)
    redirect_uri = f"{settings.backend_public_url.rstrip('/')}/api/auth/sso/{provider}/callback"
    return await client.authorize_redirect(request, redirect_uri)


def _microsoft_issuer_ok(claims: Any, value: str) -> bool:
    match = _MS_ISSUER.match(value or "")
    return bool(match and match.group(1).lower() == str(claims.get("tid", "")).lower())


class SsoLinkError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def link_sso_user(db: Session, provider: str, claims: dict[str, Any]) -> User:
    """Busca la identidad externa; si no existe, crea el usuario local."""
    if provider == "microsoft":
        oid, tid = claims.get("oid"), claims.get("tid")
        subject = f"{tid}:{oid}" if oid and tid else None
        email = claims.get("email") or claims.get("preferred_username")
    else:
        subject = claims.get("sub")
        email = claims.get("email") if claims.get("email_verified", True) else None
    if not subject or not email:
        raise SsoLinkError("sso_missing_claims")
    email = str(email).lower()
    identity = db.scalar(select(SsoIdentity).where(SsoIdentity.provider == provider, SsoIdentity.subject == subject))
    if identity is not None:
        user = identity.user
    else:
        if db.scalar(select(User).where(User.email == email)):
            # No se vincula automáticamente una cuenta existente (evita tomas de cuenta).
            raise SsoLinkError("sso_email_in_use")
        user = User(email=email, name=str(claims.get("name") or email.split("@")[0])[:120], password_hash=None)
        db.add(user)
        db.flush()
        db.add(SsoIdentity(user_id=user.id, provider=provider, subject=subject, email=email))
        log_activity(db, None, user, "user.registered", {"provider": provider})
    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)
    return user


def _link_in_new_session(provider: str, claims: dict[str, Any]) -> User:
    db = SessionLocal()
    try:
        return link_sso_user(db, provider, claims)
    finally:
        db.close()


@router.get("/sso/{provider}/callback")
async def sso_callback(provider: str, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    from authlib.integrations.starlette_client import OAuthError

    client = get_oauth_client(provider, settings)
    login_url = f"{settings.frontend_url.rstrip('/')}/login"
    kwargs: dict[str, Any] = {}
    if provider == "microsoft":
        kwargs["claims_options"] = {"iss": {"essential": True, "validate": _microsoft_issuer_ok}}
    try:
        token = await client.authorize_access_token(request, **kwargs)
    except OAuthError as exc:
        logger.warning("SSO rechazado", extra={"provider": provider, "error": str(exc)[:200]})
        return RedirectResponse(f"{login_url}?error=sso_failed", status_code=302)
    except Exception as exc:  # noqa: BLE001 - proveedor caído o red
        logger.warning("SSO no disponible", extra={"provider": provider, "error": str(exc)[:200]})
        return RedirectResponse(f"{login_url}?error=sso_unavailable", status_code=302)
    claims = dict(token.get("userinfo") or {})
    try:
        user = await run_in_threadpool(_link_in_new_session, provider, claims)
    except SsoLinkError as exc:
        return RedirectResponse(f"{login_url}?error={exc.code}", status_code=302)
    response = RedirectResponse(f"{settings.frontend_url.rstrip('/')}/", status_code=302)
    set_session_cookie(response, create_access_token(user.id, settings), settings)
    return response
