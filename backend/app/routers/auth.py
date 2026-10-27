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

