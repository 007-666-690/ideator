"""Dependencias de FastAPI: usuario autenticado y control de acceso a proyectos.

La autorización SIEMPRE se valida aquí, en el backend:
- sin identidad válida            -> 401
- el proyecto no existe           -> 404
- autenticado pero sin membresía  -> 403
- miembro con rol insuficiente    -> 403
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .errors import ApiError
from .models import ROLE_RANK, Project, ProjectMember, RevokedToken, User
from .observability import set_current_user
from .security import decode_access_token


def extract_token(request: Request, settings: Settings) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(settings.session_cookie_name)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = extract_token(request, settings)
    if not token:
        raise ApiError(401, "not_authenticated", "Debes iniciar sesión.")
    claims = decode_access_token(token, settings)
    if db.get(RevokedToken, claims.jti) is not None:
        raise ApiError(401, "session_revoked", "Esta sesión fue cerrada. Vuelve a iniciar sesión.")
    user = db.get(User, claims.user_id)
    if user is None:
        raise ApiError(401, "invalid_token", "Sesión inválida. Vuelve a iniciar sesión.")
    set_current_user(str(user.id))
    return user


@dataclass
class ProjectAccess:
    project: Project
    member: ProjectMember
    user: User

    @property
    def role(self) -> str:
        return self.member.role


def load_project_access(db: Session, project_id: uuid.UUID, user: User, min_role: str) -> ProjectAccess:
    project = db.get(Project, project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "El proyecto no existe.")
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
    )
    if member is None:
        raise ApiError(403, "forbidden", "No tienes acceso a este proyecto.")
    if ROLE_RANK.get(member.role, 0) < ROLE_RANK[min_role]:
        raise ApiError(
            403,
            "insufficient_role",
            f"Tu rol ({member.role}) no permite esta acción. Se requiere {min_role} o superior.",
        )
    return ProjectAccess(project=project, member=member, user=user)


def require_role(min_role: str):
    def dependency(
        project_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> ProjectAccess:
        return load_project_access(db, project_id, user, min_role)

    return dependency


viewer_access = require_role("viewer")
editor_access = require_role("editor")
owner_access = require_role("owner")
