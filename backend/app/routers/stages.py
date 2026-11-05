"""Etapas del proceso de definición."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..deps import ProjectAccess, editor_access, get_current_user, viewer_access
from ..errors import ApiError
from ..ideator import engine
from ..ideator.architectures import BASE_ARCHITECTURES
from ..ideator.engine import iso, stage_view, stages_by_kind, user_ref
from ..ideator.llm import LLMClient, LLMError, get_llm
from ..models import STAGE_KINDS, Message, Question, User

router = APIRouter(prefix="/api", tags=["stages"])


class VersionIn(BaseModel):
    version: int


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    answer: str = Field(min_length=1, max_length=4000)


class TurnIn(BaseModel):
    version: int
    answers: list[AnswerIn] = Field(default_factory=list, max_length=20)
    message: str | None = Field(default=None, max_length=4000)


class GenerateIn(BaseModel):
    version: int
    instructions: str | None = Field(default=None, max_length=4000)


class StageDataIn(BaseModel):
    version: int
    data: dict[str, Any]
    summary: str | None = Field(default=None, max_length=200)


class BriefIn(BaseModel):
    version: int
    brief: dict[str, Any]


class SelectIn(BaseModel):
    version: int
    scenario_id: str = Field(min_length=1, max_length=10)


class DismissIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class FindingIn(BaseModel):
    version: int
    resolution: Literal["fixed", "accepted", "open"]
    note: str = Field(default="", max_length=1000)


class AssumptionsIn(BaseModel):
    version: int
    ids: list[str] | None = None


def llm_dep(settings: Settings = Depends(get_settings)) -> LLMClient:
    try:
        return get_llm(settings)
    except LLMError as exc:
        raise ApiError(exc.status, exc.code, str(exc)) from exc


def question_out(q: Question) -> dict[str, Any]:
    return {
        "id": str(q.id),
        "code": q.code,
        "text": q.text,
        "rationale": q.rationale,
        "blocking": q.blocking,
        "affects": q.affects,
        "options": q.options,
        "section": q.section,
        "status": q.status,
        "answer": q.answer,
        "answered_by": user_ref(q.answerer),
        "answered_at": iso(q.answered_at),
        "round": q.round,
        "created_at": iso(q.created_at),
    }


def full_stage(db: Session, access: ProjectAccess, kind: str) -> dict[str, Any]:
    if kind not in STAGE_KINDS:
        raise ApiError(404, "stage_not_found", f"La etapa '{kind}' no existe.")
    db.expire_all()
    stages = stages_by_kind(db, access.project.id)
    view = stage_view(db, access.project, stages, kind)
    if kind == "product":
        questions = db.scalars(select(Question).where(Question.project_id == access.project.id).order_by(Question.created_at, Question.code)).all()
        messages = db.scalars(select(Message).where(Message.project_id == access.project.id).order_by(Message.created_at)).all()
        view["questions"] = [question_out(q) for q in questions]
        view["messages"] = [
            {"id": str(m.id), "role": m.role, "author": user_ref(m.author), "content": m.content, "created_at": iso(m.created_at)} for m in messages
        ]
    view["my_role"] = access.role
    return view


@router.get("/architectures")
def architectures(_user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return BASE_ARCHITECTURES


@router.get("/projects/{project_id}/stages")
def list_stages(access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stages = stages_by_kind(db, access.project.id)
    return [engine.stage_summary(stages[k]) for k in STAGE_KINDS]


@router.get("/projects/{project_id}/stages/{kind}")
def get_stage(kind: str, access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    return full_stage(db, access, kind)


@router.get("/projects/{project_id}/questions")
def list_questions(
    access: ProjectAccess = Depends(viewer_access),
    db: Session = Depends(get_db),
    status: str | None = Query(None, pattern="^(open|answered|resolved|dismissed)$"),
) -> list[dict[str, Any]]:
    query = select(Question).where(Question.project_id == access.project.id)
    if status:
        query = query.where(Question.status == status)
    return [question_out(q) for q in db.scalars(query.order_by(Question.created_at, Question.code)).all()]


# --- Producto ---------------------------------------------------------------


@router.post("/projects/{project_id}/product/start")
def product_start(body: VersionIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    engine.product_start(db, llm, access.project, access.user, body.version)
    return full_stage(db, access, "product")


@router.post("/projects/{project_id}/product/turn")
def product_turn(body: TurnIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    answers = [(a.question_id, a.answer) for a in body.answers]
    engine.product_turn(db, llm, access.project, access.user, body.version, answers, body.message)
    return full_stage(db, access, "product")


@router.post("/projects/{project_id}/questions/{question_id}/dismiss")
def dismiss_question(question_id: uuid.UUID, body: DismissIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    engine.dismiss_question(db, access.project, access.user, question_id, body.reason)
    return full_stage(db, access, "product")


@router.put("/projects/{project_id}/stages/product")
def save_brief(body: BriefIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    engine.save_brief(db, access.project, access.user, body.brief, body.version)
    return full_stage(db, access, "product")


@router.post("/projects/{project_id}/product/assumptions/accept")
def accept_assumptions(body: AssumptionsIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    engine.accept_assumptions(db, access.project, access.user, body.ids, body.version)
    return full_stage(db, access, "product")


# --- Datos, API, pantallas, arquitectura ----------------------------------------


@router.post("/projects/{project_id}/stages/{kind}/generate")
def generate(kind: str, body: GenerateIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    if kind == "architecture":
        engine.architecture_generate(db, llm, access.project, access.user, body.version, body.instructions)
    else:
        engine.generate_stage(db, llm, access.project, access.user, kind, body.version, body.instructions)
    return full_stage(db, access, kind)


@router.put("/projects/{project_id}/stages/{kind}")
def save_stage(kind: str, body: StageDataIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    engine.save_stage_data(db, access.project, access.user, kind, body.data, body.version, body.summary)
    return full_stage(db, access, kind)


@router.post("/projects/{project_id}/architecture/evaluate")
def architecture_evaluate(body: VersionIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    engine.architecture_evaluate(db, llm, access.project, access.user, body.version)
    return full_stage(db, access, "architecture")


@router.post("/projects/{project_id}/architecture/select")
def architecture_select(body: SelectIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    engine.architecture_select(db, access.project, access.user, body.scenario_id, body.version)
    return full_stage(db, access, "architecture")


# --- Aprobación ------------------------------------------------------------------


@router.post("/projects/{project_id}/stages/{kind}/approve")
def approve(kind: str, body: VersionIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    if kind not in STAGE_KINDS:
        raise ApiError(404, "stage_not_found", f"La etapa '{kind}' no existe.")
    engine.approve_stage(db, access.project, access.user, kind, body.version)
    return full_stage(db, access, kind)


@router.get("/projects/{project_id}/stages/{kind}/markdown")
def stage_markdown_export(kind: str, access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    return engine.export_stage(db, access.project, kind)


@router.delete("/projects/{project_id}/stages/{kind}/approval")
def withdraw_approval(kind: str, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    if kind not in STAGE_KINDS:
        raise ApiError(404, "stage_not_found", f"La etapa '{kind}' no existe.")
    engine.withdraw_approval(db, access.project, access.user, kind)
    return full_stage(db, access, kind)


@router.post("/projects/{project_id}/stages/{kind}/reopen")
def reopen(kind: str, body: VersionIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    if kind not in STAGE_KINDS:
        raise ApiError(404, "stage_not_found", f"La etapa '{kind}' no existe.")
    engine.reopen_stage(db, access.project, access.user, kind, body.version)
    return full_stage(db, access, kind)


# --- Revisión ----------------------------------------------------------------------


@router.post("/projects/{project_id}/review/run")
def review_run(body: VersionIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db), llm: LLMClient = Depends(llm_dep)) -> dict[str, Any]:
    engine.run_review(db, llm, access.project, access.user, body.version)
    return full_stage(db, access, "review")


@router.post("/projects/{project_id}/review/findings/{finding_id}")
def review_finding(finding_id: str, body: FindingIn, access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    engine.resolve_finding(db, access.project, access.user, finding_id, body.resolution, body.note, body.version)
    return full_stage(db, access, "review")
