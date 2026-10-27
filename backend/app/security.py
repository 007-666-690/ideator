"""Contraseñas, tokens de sesión y protección contra fuerza bruta."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Response

from .config import Settings
from .errors import ApiError

_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "session_expired", "Tu sesión expiró. Vuelve a iniciar sesión.") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "invalid_token", "Sesión inválida. Vuelve a iniciar sesión.") from exc
    if payload.get("typ") != "access":
        raise ApiError(401, "invalid_token", "Sesión inválida. Vuelve a iniciar sesión.")
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise ApiError(401, "invalid_token", "Sesión inválida. Vuelve a iniciar sesión.") from exc


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=settings.session_cookie_name, path="/", samesite="lax", secure=settings.cookie_secure)


class LoginThrottle:
    """Limita intentos fallidos de login por clave (correo + IP) en una ventana de tiempo."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: int) -> deque[float]:
        attempts = self._attempts[key]
        limit = time.monotonic() - window
        while attempts and attempts[0] < limit:
            attempts.popleft()
        return attempts

    def check(self, key: str, max_attempts: int, window: int) -> None:
        with self._lock:
            if len(self._prune(key, window)) >= max_attempts:
                raise ApiError(429, "too_many_attempts", "Demasiados intentos fallidos. Espera unos minutos.")

    def fail(self, key: str, window: int) -> None:
        with self._lock:
            self._prune(key, window).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_throttle = LoginThrottle()
