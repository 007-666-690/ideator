"""Proyectos: privados por defecto; solo los miembros pueden verlos."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ProjectAccess, editor_access, get_current_user, owner_access, viewer_access
from ..ideator.engine import create_stages, iso, log_activity, question_counts, stage_summary, user_ref
from ..models import STAGE_APPROVED, STAGE_KINDS, ActivityLog, Document, Project, ProjectMember, Stage, StageRevision, User

router = APIRouter(prefix="/api", tags=["projects"])

ACTION_LABELS = {
    "project.created": "creó el proyecto",
    "project.updated": "editó los datos del proyecto",
    "member.invited": "invitó a",
    "invitation.revoked": "anuló la invitación de",
    "invitation.accepted": "se unió al proyecto",
    "invitation.declined": "rechazó la invitación",
    "member.role_changed": "cambió el rol de",
    "member.removed": "quitó del proyecto a",
    "member.left": "salió del proyecto",
    "product.started": "comenzó la definición",
    "product.answers": "respondió preguntas",
    "product.round": "procesó una ronda con la IA",
    "question.dismissed": "descartó una pregunta",
    "stage.edited": "editó",
    "stage.generated": "generó con IA",
    "stage.approved": "aprobó",
    "stage.reopened": "reabrió",
    "architecture.evaluated": "evaluó las arquitecturas",
    "architecture.selected": "seleccionó la arquitectura",
    "assumptions.accepted": "aceptó supuestos",
    "review.run": "ejecutó la revisión de consistencia",
    "review.finding": "resolvió un hallazgo",
    "documents.generated": "generó los documentos",
}


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    idea: str = Field(min_length=10, max_length=6000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    idea: str | None = Field(default=None, min_length=10, max_length=6000)


def current_stage_kind(stages: list[Stage]) -> str:
    by_kind = {s.kind: s for s in stages}
    for kind in STAGE_KINDS:
        if by_kind[kind].status != STAGE_APPROVED:
            return kind
    return "documents"


def project_view(db: Session, project: Project, member: ProjectMember) -> dict[str, Any]:
    stages = sorted(project.stages, key=lambda s: STAGE_KINDS.index(s.kind))
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id).order_by(ProjectMember.created_at)).all()
    docs = db.scalar(select(func.count()).select_from(Document).where(Document.project_id == project.id)) or 0
    return {
        "id": str(project.id),
        "name": project.name,
        "idea": project.idea,
        "owner": user_ref(project.owner),
        "my_role": member.role,
        "created_at": iso(project.created_at),
        "updated_at": iso(project.updated_at),
        "current_stage": current_stage_kind(stages),
        "stages": [stage_summary(s) for s in stages],
        "members": [{"user": user_ref(m.user), "role": m.role, "added_at": iso(m.created_at)} for m in members],
        "questions": question_counts(db, project.id),
        "documents": docs,
    }


@router.get("/projects")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Project, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.updated_at.desc())
    ).all()
    result = []
    for project, member in rows:
        stages = sorted(project.stages, key=lambda s: STAGE_KINDS.index(s.kind))
        result.append(
            {
                "id": str(project.id),
                "name": project.name,
                "idea": project.idea[:240],
                "my_role": member.role,
                "owner": user_ref(project.owner),
                "updated_at": iso(project.updated_at),
                "current_stage": current_stage_kind(stages),
                "approved_stages": sum(1 for s in stages if s.status == STAGE_APPROVED),
                "members": len(project.members),
            }
        )
    return result


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    project = Project(name=body.name.strip(), idea=body.idea.strip(), owner_id=user.id)
    db.add(project)
    db.flush()
    member = ProjectMember(project_id=project.id, user_id=user.id, role="owner", added_by=user.id)
    db.add(member)
    create_stages(db, project)
    log_activity(db, project.id, user, "project.created", {"name": project.name})
    db.commit()
    db.refresh(project)
    return project_view(db, project, member)


@router.get("/projects/{project_id}")
def get_project(access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    return project_view(db, access.project, access.member)


@router.patch("/projects/{project_id}")
def update_project(body: ProjectPatch, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    changed = {}
    if body.name is not None and body.name.strip() != access.project.name:
        access.project.name = body.name.strip()
        changed["name"] = access.project.name
    if body.idea is not None and body.idea.strip() != access.project.idea:
        access.project.idea = body.idea.strip()
        changed["idea"] = True
    if changed:
        log_activity(db, access.project.id, access.user, "project.updated", changed)
        db.commit()
    return project_view(db, access.project, access.member)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(access: ProjectAccess = Depends(owner_access), db: Session = Depends(get_db)) -> Response:
    db.delete(access.project)
    db.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/activity")
def project_activity(
    access: ProjectAccess = Depends(viewer_access),
    db: Session = Depends(get_db),
    after: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    query = select(ActivityLog).where(ActivityLog.project_id == access.project.id)
    if after:
        query = query.where(ActivityLog.id > after).order_by(ActivityLog.id.asc())
    else:
        query = query.order_by(ActivityLog.id.desc())
    rows = db.scalars(query.limit(limit)).all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "label": ACTION_LABELS.get(a.action, a.action),
            "details": a.details,
            "user": user_ref(a.user),
            "created_at": iso(a.created_at),
        }
        for a in rows
    ]


@router.get("/projects/{project_id}/sync")
def project_sync(access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Estado liviano para que cada cliente detecte cambios de otros usuarios."""
    stages = db.scalars(select(Stage).where(Stage.project_id == access.project.id)).all()
    last = db.scalar(select(func.max(ActivityLog.id)).where(ActivityLog.project_id == access.project.id)) or 0
    return {
        "stages": {s.kind: stage_summary(s) for s in stages},
        "last_activity_id": last,
        "questions": question_counts(db, access.project.id),
    }


@router.get("/projects/{project_id}/revisions")
def stage_revisions(
    access: ProjectAccess = Depends(viewer_access),
    db: Session = Depends(get_db),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    query = (
        select(StageRevision, Stage.kind)
        .join(Stage, Stage.id == StageRevision.stage_id)
        .where(Stage.project_id == access.project.id)
        .order_by(StageRevision.created_at.desc())
        .limit(limit)
    )
    if kind:
        query = query.where(Stage.kind == kind)
    return [
        {
            "kind": k,
            "version": r.version,
            "source": r.source,
            "summary": r.summary,
            "author": user_ref(r.author),
            "created_at": iso(r.created_at),
        }
        for r, k in db.execute(query).all()
    ]


@router.get("/projects/{project_id}/revisions/{kind}/{version}")
def stage_revision_detail(
    kind: str, version: int, access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)
) -> dict[str, Any]:
    from ..errors import ApiError

    row = db.execute(
        select(StageRevision)
        .join(Stage, Stage.id == StageRevision.stage_id)
        .where(Stage.project_id == access.project.id, Stage.kind == kind, StageRevision.version == version)
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "revision_not_found", "Esa versión no existe.")
    return {"kind": kind, "version": row.version, "source": row.source, "summary": row.summary, "author": user_ref(row.author), "created_at": iso(row.created_at), "content": row.content}


def _uuid(value: str) -> uuid.UUID:  # pragma: no cover - utilidad
    return uuid.UUID(value)
