"""Orquestación del proceso de definición.

Reglas del flujo:
- Las etapas se aprueban en orden: producto → datos → API → pantallas → arquitectura → revisión.
- Una etapa solo se genera o aprueba si las anteriores están aprobadas.
- Toda modificación exige la versión vigente de la etapa (control optimista): si otra
  persona la cambió antes, se responde 409 para no pisar su trabajo.
- Reabrir una etapa aprobada deja "desactualizadas" (stale) las etapas siguientes.
- Cada cambio queda en el historial (stage_revisions) y en la actividad del proyecto.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import (
    STAGE_APPROVED,
    STAGE_IN_PROGRESS,
    STAGE_KINDS,
    STAGE_LABELS,
    STAGE_LOCKED,
    STAGE_STALE,
    ActivityLog,
    Document,
    Message,
    Project,
    ProjectMember,
    Question,
    Stage,
    StageApproval,
    StageRevision,
    User,
    utcnow,
)
from . import prompts
from .architectures import ARCHITECTURE_IDS, BASE_ARCHITECTURES, get_architecture
from .documents import ARCHITECTURE_FILENAME, PRODUCT_FILENAME, architecture_markdown, product_spec_markdown, stage_markdown
from .llm import LLMClient, LLMError
from .render import ddl, mermaid_er, navigation_map
from .schemas import (
    STAGE_SCHEMAS,
    ApiSpec,
    ArchitectureEvaluation,
    ArchitectureSpec,
    ConsistencyReview,
    DataModel,
    FrontendSpec,
    ProductBrief,
    ProductTurn,
    empty_brief,
)
from .validation import (
    derive_relationships,
    has_errors,
    issue,
    junction_tables,
    product_checklist,
    validate_api,
    validate_architecture,
    validate_data_model,
    validate_frontend,
    validate_product,
)

logger = logging.getLogger("ideator.engine")

GENERATION_TIMEOUT = timedelta(minutes=10)
MAX_NEW_QUESTIONS = 5
UPSTREAM: dict[str, list[str]] = {kind: list(STAGE_KINDS[:i]) for i, kind in enumerate(STAGE_KINDS)}
EFFORT = {
    "product_turn": "low",
    "data_model": "medium",
    "api_spec": "medium",
    "frontend_spec": "low",
    "architecture_eval": "low",
    "architecture_spec": "low",
    "consistency_review": "medium",
}
GENERATION_TASKS: dict[str, tuple[str, type[BaseModel], str]] = {
    "data_model": ("data_model", DataModel, prompts.DATA_MODEL_SYSTEM),
    "api": ("api_spec", ApiSpec, prompts.API_SYSTEM),
    "frontend": ("frontend_spec", FrontendSpec, prompts.FRONTEND_SYSTEM),
}
AREA_BY_KIND = {"product": "producto", "data_model": "datos", "api": "api", "frontend": "pantallas", "architecture": "arquitectura"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    dt = aware(dt)
    return dt.isoformat() if dt else None


def user_ref(user: User | None) -> dict[str, Any] | None:
    return {"id": str(user.id), "name": user.name, "email": user.email} if user else None


def log_activity(db: Session, project_id: uuid.UUID | None, user: User | None, action: str, details: dict | None = None) -> None:
    db.add(ActivityLog(project_id=project_id, user_id=user.id if user else None, action=action, details=details or {}))


def initial_content(kind: str, project_name: str) -> dict[str, Any]:
    if kind == "product":
        return {"brief": empty_brief(project_name).model_dump(mode="json"), "contradictions": [], "round": 0, "started": False}
    if kind == "architecture":
        return {"evaluation": None, "selected": None, "data": None, "based_on": {}}
    if kind == "review":
        return {"findings": [], "warnings": [], "summary": "", "ran_at": None, "based_on": {}}
    return {"data": None, "based_on": {}}


def create_stages(db: Session, project: Project) -> None:
    for kind in STAGE_KINDS:
        db.add(
            Stage(
                project_id=project.id,
                kind=kind,
                status=STAGE_IN_PROGRESS if kind == "product" else STAGE_LOCKED,
                content=initial_content(kind, project.name),
                version=1,
            )
        )


def stages_by_kind(db: Session, project_id: uuid.UUID) -> dict[str, Stage]:
    rows = db.scalars(select(Stage).where(Stage.project_id == project_id)).all()
    return {s.kind: s for s in rows}


def get_stage(db: Session, project_id: uuid.UUID, kind: str) -> Stage:
    if kind not in STAGE_KINDS:
        raise ApiError(404, "stage_not_found", f"La etapa '{kind}' no existe.")
    stage = db.scalar(select(Stage).where(Stage.project_id == project_id, Stage.kind == kind))
    if stage is None:
        raise ApiError(404, "stage_not_found", f"La etapa '{kind}' no existe.")
    return stage


def is_generating(stage: Stage) -> bool:
    since = aware(stage.generating_since)
    return bool(since and utcnow() - since < GENERATION_TIMEOUT)


def check_version(stage: Stage, version: int) -> None:
    if version != stage.version:
        raise ApiError(
            409,
            "version_conflict",
            "Otra persona modificó esta etapa mientras trabajabas. Recarga para ver la versión vigente.",
            {
                "current_version": stage.version,
                "your_version": version,
                "updated_by": stage.updater.name if stage.updater else None,
                "updated_at": iso(stage.updated_at),
            },
        )


def require_editable(stage: Stage) -> None:
    if stage.status == STAGE_LOCKED:
        raise ApiError(409, "stage_locked", f"«{STAGE_LABELS[stage.kind]}» se habilita al aprobar la etapa anterior.")
    if stage.status == STAGE_APPROVED:
        raise ApiError(409, "stage_approved", f"«{STAGE_LABELS[stage.kind]}» está aprobada. Reábrela para modificarla.")
    if is_generating(stage):
        raise ApiError(409, "generation_in_progress", "La IA está trabajando en esta etapa. Espera a que termine.")


def require_upstream_approved(stages: dict[str, Stage], kind: str) -> None:
    for up in UPSTREAM[kind]:
        if stages[up].status != STAGE_APPROVED:
            raise ApiError(409, "upstream_not_approved", f"Primero debes aprobar «{STAGE_LABELS[up]}».")


def commit_revision(db: Session, stage: Stage, content: dict[str, Any], user: User, source: str, summary: str) -> None:
    stage.content = copy.deepcopy(content)
    stage.version += 1
    stage.updated_by = user.id
    stage.updated_at = utcnow()
    db.add(
        StageRevision(stage_id=stage.id, version=stage.version, content=stage.content, author_id=user.id, source=source, summary=summary[:300])
    )


def begin_generation(db: Session, stage: Stage) -> None:
    if is_generating(stage):
        raise ApiError(409, "generation_in_progress", "La IA ya está trabajando en esta etapa. Espera a que termine.")
    stage.generating_since = utcnow()
    db.commit()


def end_generation(db: Session, stage: Stage) -> None:
    stage.generating_since = None
    db.commit()


def llm_failure(exc: LLMError, extra: str = "") -> ApiError:
    return ApiError(exc.status, exc.code, f"{exc}{(' ' + extra) if extra else ''}")


def brief_of(stage: Stage) -> ProductBrief:
    return ProductBrief.model_validate(stage.content["brief"])


def data_of(stage: Stage, schema: type[BaseModel]) -> Any:
    data = stage.content.get("data")
    if not data:
        return None
    try:
        return schema.model_validate(data)
    except ValidationError:
        logger.exception("Contenido inválido en la etapa %s", stage.kind)
        return None


def evaluation_of(stage: Stage) -> ArchitectureEvaluation | None:
    data = stage.content.get("evaluation")
    return ArchitectureEvaluation.model_validate(data) if data else None


def _call(llm: LLMClient, task: str, system: str, user_prompt: str, schema: type[BaseModel]) -> Any:
    return llm.complete(task=task, system=system, user=user_prompt, schema=schema, effort=EFFORT.get(task))


# ---------------------------------------------------------------------------
# Validación por etapa (se usa al mostrar y al aprobar)
# ---------------------------------------------------------------------------


def question_counts(db: Session, project_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(Question.status, Question.blocking, func.count()).where(Question.project_id == project_id).group_by(Question.status, Question.blocking)
    ).all()
    counts = {"open": 0, "open_blocking": 0, "answered": 0}
    for status, blocking, n in rows:
        if status == "open":
            counts["open"] += n
            if blocking:
                counts["open_blocking"] += n
        elif status == "answered":
            counts["answered"] += n
    return counts


def review_outdated(stages: dict[str, Stage]) -> bool:
    based_on = stages["review"].content.get("based_on") or {}
    if not based_on:
        return True
    return any(based_on.get(k) != stages[k].version for k in STAGE_KINDS[:-1])


def stage_issues(db: Session, project: Project, stages: dict[str, Stage], kind: str) -> tuple[list[dict], dict[str, Any]]:
    stage = stages[kind]
    brief = brief_of(stages["product"])
    extra: dict[str, Any] = {}
    if kind == "product":
        counts = question_counts(db, project.id)
        extra["checklist"] = product_checklist(brief, counts["open_blocking"])
        extra["questions"] = counts
        if not stage.content.get("started"):
            return [issue("error", "product.not_started", "Aún no comienza la definición.")], extra
        issues = validate_product(brief, counts["open_blocking"])
        if counts["answered"]:
            issues.append(issue("error", "product.pending_answers", f"Hay {counts['answered']} respuesta(s) que la IA aún no procesa."))
        return issues, extra

    if kind == "data_model":
        model = data_of(stage, DataModel)
        if model is None:
            return [issue("error", "dm.missing", "Aún no hay un modelo de datos.")], extra
        extra["mermaid"] = mermaid_er(model)
        extra["ddl"] = ddl(model)
        extra["relationships"] = derive_relationships(model)
        extra["junctions"] = junction_tables(model)
        return validate_data_model(model, brief), extra

    if kind == "api":
        spec = data_of(stage, ApiSpec)
        if spec is None:
            return [issue("error", "api.missing", "Aún no hay una especificación de API.")], extra
        return validate_api(spec, data_of(stages["data_model"], DataModel), brief), extra

    if kind == "frontend":
        spec = data_of(stage, FrontendSpec)
        if spec is None:
            return [issue("error", "fe.missing", "Aún no hay pantallas definidas.")], extra
        extra["navigation_map"] = navigation_map(spec)
        return validate_frontend(spec, data_of(stages["api"], ApiSpec), brief), extra

    if kind == "architecture":
        extra["scenarios"] = BASE_ARCHITECTURES
        spec = data_of(stage, ArchitectureSpec)
        if spec is None:
            return [issue("error", "arch.missing", "Aún no se detalla la arquitectura.")], extra
        issues = validate_architecture(spec, ARCHITECTURE_IDS)
        if spec.scenario_id != stage.content.get("selected"):
            issues.append(issue("error", "arch.mismatch", "La arquitectura detallada no corresponde al escenario seleccionado. Vuelve a generarla."))
        return issues, extra

    # review
    issues = []
    content = stage.content
    if not content.get("ran_at"):
        issues.append(issue("error", "review.not_run", "Aún no se ejecuta la revisión de consistencia."))
    elif review_outdated(stages):
        issues.append(issue("error", "review.outdated", "Hubo cambios después de la última revisión. Vuelve a ejecutarla."))
    open_critical = [f for f in content.get("findings", []) if f["severity"] == "critica" and f["status"] == "open"]
    for f in open_critical:
        issues.append(issue("error", "review.critical", f"{f['id']}: {f['description']}", f["id"]))
    for k in ("data_model", "api", "frontend", "architecture"):
        if k in stages and rejects_assumptions(stages[k].content):
            issues.append(
                issue(
                    "error",
                    "review.assumptions_contradicted",
                    f"«{STAGE_LABELS[k]}» dice que hay supuestos no aceptados y no los aplica. "
                    "Reábrela y pide a la IA que aplique los supuestos de la definición.",
                )
            )
    pending = [a.id for a in brief.assumptions if not a.accepted]
    if pending:
        issues.append(issue("error", "review.assumptions", f"Supuestos sin aceptar: {', '.join(pending)}"))
    extra["assumptions"] = [a.model_dump() for a in brief.assumptions]
    return issues, extra


_REJECTED_ASSUMPTION = __import__("re").compile(
    r"supuestos?\b[^.]{0,120}?\bno\s+(?:fue|fueron|ha\s+sido|han\s+sido|est[aá]n?\s+)?\s*aceptad|no\s+aceptad\w*\s+(?:como\s+)?supuesto",
    __import__("re").IGNORECASE,
)


def rejects_assumptions(content: Any) -> bool:
    """True si el contenido de una etapa trata los supuestos de la definición como rechazados."""
    import json as _json

    return bool(_REJECTED_ASSUMPTION.search(_json.dumps(content, ensure_ascii=False)))


def stage_view(db: Session, project: Project, stages: dict[str, Stage], kind: str) -> dict[str, Any]:
    stage = stages[kind]
    issues, extra = stage_issues(db, project, stages, kind)
    return {
        "kind": kind,
        "label": STAGE_LABELS[kind],
        "status": stage.status,
        "version": stage.version,
        "updated_at": iso(stage.updated_at),
        "updated_by": user_ref(stage.updater),
        "approved_at": iso(stage.approved_at),
        "approved_by": user_ref(stage.approver),
        "approved_version": stage.approved_version,
        "generating": is_generating(stage),
        "content": stage.content,
        "issues": issues,
        "can_approve": stage.status in (STAGE_IN_PROGRESS, STAGE_STALE)
        and all(stages[u].status == STAGE_APPROVED for u in UPSTREAM[kind])
        and not has_errors(issues),
        "approvals": approvals_view(db, project, stage),
        **extra,
    }


def stage_summary(stage: Stage) -> dict[str, Any]:
    return {
        "kind": stage.kind,
        "label": STAGE_LABELS[stage.kind],
        "status": stage.status,
        "version": stage.version,
        "updated_at": iso(stage.updated_at),
        "generating": is_generating(stage),
    }


# ---------------------------------------------------------------------------
# Etapa 1: definición del producto
# ---------------------------------------------------------------------------


def _ordered_questions(db: Session, project_id: uuid.UUID, statuses: tuple[str, ...]) -> list[Question]:
    return list(
        db.scalars(
            select(Question).where(Question.project_id == project_id, Question.status.in_(statuses)).order_by(Question.created_at, Question.code)
        ).all()
    )


LATE_ROUND = 5


def max_new_questions(round_number: int) -> int:
    """Presupuesto de preguntas: 4 en las primeras rondas, 2 desde la tercera."""
    return MAX_NEW_QUESTIONS if round_number < 3 else 2


def _apply_turn(
    db: Session,
    project: Project,
    stage: Stage,
    turn: ProductTurn,
    user: User,
    round_number: int,
    ref_map: dict[str, Question],
    answered: list[Question],
) -> None:
    previous = brief_of(stage)
    accepted_before = {a.id: a.description for a in previous.assumptions if a.accepted}
    brief = turn.brief
    for a in brief.assumptions:
        # Solo el equipo acepta supuestos: la IA no puede marcarlos como aceptados.
        a.accepted = accepted_before.get(a.id) == a.description

    for q in answered:
        q.status = "resolved"
    for ref in turn.resolved_question_refs:
        q = ref_map.get(ref)
        if q is not None and q.status == "open":
            q.status = "resolved"
            q.answer = q.answer or "Resuelta con otras respuestas del equipo."

    total = db.scalar(select(func.count()).select_from(Question).where(Question.project_id == project.id)) or 0
    seen = {q.text.strip().lower() for q in _ordered_questions(db, project.id, ("open",))}
    created = 0
    limit = max_new_questions(round_number)
    for nq in sorted(turn.new_questions, key=lambda q: not q.blocking):
        if created >= limit or nq.text.strip().lower() in seen:
            continue
        if round_number >= LATE_ROUND and not nq.blocking:
            # En rondas tardías los detalles no bloqueantes se resuelven con supuestos, no con más preguntas.
            continue
        created += 1
        db.add(
            Question(
                project_id=project.id,
                code=f"P-{total + created:02d}",
                stage_kind="product",
                text=nq.text.strip(),
                rationale=nq.rationale.strip(),
                blocking=nq.blocking,
                affects=list(dict.fromkeys(nq.affects)),
                options=[o for o in nq.options if o.strip()][:4],
                section=nq.section[:60],
                round=round_number,
            )
        )
    if turn.assistant_message.strip():
        db.add(Message(project_id=project.id, stage_kind="product", role="assistant", content=turn.assistant_message.strip()))

    content = {
        "brief": brief.model_dump(mode="json"),
        "contradictions": turn.contradictions,
        "round": round_number,
        "started": True,
    }
    summary = f"Ronda {round_number}: {len(answered)} respuesta(s) procesada(s), {created} pregunta(s) nueva(s)"
    commit_revision(db, stage, content, user, "ai", summary)
    log_activity(db, project.id, user, "product.round", {"round": round_number, "answered": len(answered), "new_questions": created})


def _run_product_round(db: Session, llm: LLMClient, project: Project, user: User, stage: Stage) -> None:
    begin_generation(db, stage)
    version_at_start = stage.version
    try:
        brief = brief_of(stage)
        answered = _ordered_questions(db, project.id, ("answered",))
        open_qs = _ordered_questions(db, project.id, ("open",))
        ref_map: dict[str, Question] = {}
        answered_refs, open_refs = [], []
        for i, q in enumerate(answered + open_qs, start=1):
            ref = f"Q{i}"
            ref_map[ref] = q
            (answered_refs if q in answered else open_refs).append((ref, q))
        last_assistant = db.scalar(
            select(func.max(Message.created_at)).where(Message.project_id == project.id, Message.role == "assistant")
        )
        msg_query = select(Message).where(Message.project_id == project.id, Message.role == "user").order_by(Message.created_at)
        if last_assistant is not None:
            msg_query = msg_query.where(Message.created_at > last_assistant)
        recent = [(m.author.name if m.author else "equipo", m.content) for m in db.scalars(msg_query).all()][-6:]
        open_blocking = sum(1 for q in open_qs if q.blocking)
        round_number = int(stage.content.get("round", 0)) + 1
        user_prompt = prompts.product_user_prompt(
            project_name=project.name,
            idea=project.idea,
            brief=brief,
            open_questions=open_refs,
            answered=answered_refs,
            messages=recent,
            checklist=product_checklist(brief, open_blocking),
            round_number=round_number,
        )
        turn = _call(llm, "product_turn", prompts.PRODUCT_SYSTEM, user_prompt, ProductTurn)
    except LLMError as exc:
        end_generation(db, stage)
        raise llm_failure(exc, "Las respuestas quedaron guardadas: puedes volver a procesarlas.") from exc
    except Exception:
        end_generation(db, stage)
        raise

    db.refresh(stage)
    if stage.version != version_at_start:
        end_generation(db, stage)
        raise ApiError(409, "version_conflict", "La definición cambió mientras la IA trabajaba. Tus respuestas quedaron guardadas; vuelve a procesarlas.")
    _apply_turn(db, project, stage, turn, user, round_number, ref_map, [q for _, q in answered_refs])
    stage.generating_since = None
    db.commit()


def product_start(db: Session, llm: LLMClient, project: Project, user: User, version: int) -> None:
    stage = get_stage(db, project.id, "product")
    check_version(stage, version)
    require_editable(stage)
    if stage.content.get("started"):
        raise ApiError(409, "already_started", "La definición ya comenzó.")
    log_activity(db, project.id, user, "product.started")
    db.commit()
    _run_product_round(db, llm, project, user, stage)


def product_turn(
    db: Session,
    llm: LLMClient,
    project: Project,
    user: User,
    version: int,
    answers: list[tuple[uuid.UUID, str]],
    message: str | None,
) -> None:
    stage = get_stage(db, project.id, "product")
    check_version(stage, version)
    if stage.status in (STAGE_LOCKED, STAGE_APPROVED):
        require_editable(stage)
    if not stage.content.get("started"):
        raise ApiError(409, "not_started", "Primero comienza la definición.")
    message = (message or "").strip() or None
    pending = question_counts(db, project.id)["answered"]
    if not answers and not message and not pending:
        raise ApiError(422, "empty_turn", "Responde al menos una pregunta o escribe un mensaje.")

    for qid, text in answers:
        q = db.get(Question, qid)
        if q is None or q.project_id != project.id:
            raise ApiError(404, "question_not_found", "La pregunta no existe.")
        if q.status not in ("open", "answered"):
            raise ApiError(409, "question_closed", f"La pregunta {q.code} ya fue resuelta.")
        q.answer = text.strip()
        q.status = "answered"
        q.answered_by = user.id
        q.answered_at = utcnow()
    if message:
        db.add(Message(project_id=project.id, stage_kind="product", role="user", author_id=user.id, content=message))
    if answers or message:
        log_activity(db, project.id, user, "product.answers", {"answers": len(answers), "message": bool(message)})
    db.commit()

    if is_generating(stage):
        raise ApiError(409, "generation_in_progress", "Tus respuestas quedaron guardadas. La IA está procesando otra ronda y las incluirá en la siguiente.")
    _run_product_round(db, llm, project, user, stage)


def dismiss_question(db: Session, project: Project, user: User, question_id: uuid.UUID, reason: str) -> Question:
    q = db.get(Question, question_id)
    if q is None or q.project_id != project.id:
        raise ApiError(404, "question_not_found", "La pregunta no existe.")
    if q.status != "open":
        raise ApiError(409, "question_closed", f"La pregunta {q.code} ya no está abierta.")
    if q.blocking:
        raise ApiError(409, "blocking_question", "Una pregunta bloqueante no se puede descartar: hay que responderla.")
    stage = get_stage(db, project.id, "product")
    require_editable(stage)
    q.status = "dismissed"
    q.answer = reason.strip() or "Descartada por el equipo"
    q.answered_by = user.id
    q.answered_at = utcnow()
    log_activity(db, project.id, user, "question.dismissed", {"code": q.code})
    db.commit()
    return q


def save_brief(db: Session, project: Project, user: User, brief_data: dict[str, Any], version: int) -> None:
    stage = get_stage(db, project.id, "product")
    check_version(stage, version)
    require_editable(stage)
    try:
        brief = ProductBrief.model_validate(brief_data)
    except ValidationError as exc:
        raise ApiError(422, "invalid_content", "La definición no tiene el formato esperado.", exc.errors(include_url=False)) from exc
    content = copy.deepcopy(stage.content)
    content["brief"] = brief.model_dump(mode="json")
    commit_revision(db, stage, content, user, "user", "Edición manual de la definición")
    log_activity(db, project.id, user, "stage.edited", {"kind": "product"})
    db.commit()


def accept_assumptions(db: Session, project: Project, user: User, ids: list[str] | None, version: int) -> list[str]:
    """Aceptar supuestos no cambia la estructura del producto: no reabre etapas."""
    stages = stages_by_kind(db, project.id)
    stage = stages["product"]
    check_version(stage, version)
    if is_generating(stage):
        raise ApiError(409, "generation_in_progress", "La IA está trabajando en la definición. Espera a que termine.")
    brief = brief_of(stage)
    accepted = []
    for a in brief.assumptions:
        if not a.accepted and (ids is None or a.id in ids):
            a.accepted = True
            accepted.append(a.id)
    if not accepted:
        raise ApiError(422, "nothing_to_accept", "No hay supuestos pendientes con esos ids.")
    old_version = stage.version
    content = copy.deepcopy(stage.content)
    content["brief"] = brief.model_dump(mode="json")
    commit_revision(db, stage, content, user, "user", f"Supuestos aceptados: {', '.join(accepted)}")
    if stage.status == STAGE_APPROVED:
        stage.approved_version = stage.version
    review = stages["review"]
    based_on = dict(review.content.get("based_on") or {})
    if based_on.get("product") == old_version:
        based_on["product"] = stage.version
        review.content = {**review.content, "based_on": based_on}
    log_activity(db, project.id, user, "assumptions.accepted", {"ids": accepted})
    db.commit()
    return accepted


# ---------------------------------------------------------------------------
# Etapas 2 a 4: datos, API y pantallas
# ---------------------------------------------------------------------------


def _upstream_artifacts(stages: dict[str, Stage]) -> dict[str, Any]:
    return {
        "brief": brief_of(stages["product"]),
        "model": data_of(stages["data_model"], DataModel),
        "api": data_of(stages["api"], ApiSpec),
        "frontend": data_of(stages["frontend"], FrontendSpec),
    }


def generate_stage(db: Session, llm: LLMClient, project: Project, user: User, kind: str, version: int, instructions: str | None) -> None:
    if kind not in GENERATION_TASKS:
        raise ApiError(404, "stage_not_found", "Esta etapa no se genera con IA.")
    instructions = (instructions or "").strip() or None
    stages = stages_by_kind(db, project.id)
    stage = stages[kind]
    check_version(stage, version)
    require_editable(stage)
    require_upstream_approved(stages, kind)
    task, schema, system = GENERATION_TASKS[kind]
    up = _upstream_artifacts(stages)
    current = data_of(stage, schema)
    if instructions and current is None:
        current = None
    if kind == "data_model":
        user_prompt = prompts.data_model_user_prompt(up["brief"], current, instructions)
    elif kind == "api":
        user_prompt = prompts.api_user_prompt(up["brief"], up["model"], current, instructions)
    else:
        user_prompt = prompts.frontend_user_prompt(up["brief"], up["api"], current, instructions)

    begin_generation(db, stage)
    try:
        result = _call(llm, task, system, user_prompt, schema)
    except LLMError as exc:
        end_generation(db, stage)
        raise llm_failure(exc) from exc
    except Exception:
        end_generation(db, stage)
        raise
    db.refresh(stage)
    if stage.version != version:
        end_generation(db, stage)
        raise ApiError(409, "version_conflict", "La etapa cambió mientras la IA trabajaba. Vuelve a intentarlo.")
    content = {"data": result.model_dump(mode="json"), "based_on": {u: stages[u].approved_version for u in UPSTREAM[kind]}}
    summary = f"Cambio pedido a la IA: {instructions}" if instructions else "Propuesta generada por la IA"
    commit_revision(db, stage, content, user, "ai", summary)
    stage.generating_since = None
    log_activity(db, project.id, user, "stage.generated", {"kind": kind, "instructions": instructions})
    db.commit()


def save_stage_data(db: Session, project: Project, user: User, kind: str, data: dict[str, Any], version: int, summary: str | None) -> None:
    schema = STAGE_SCHEMAS.get(kind)
    if schema is None or kind == "product":
        raise ApiError(404, "stage_not_found", "Esta etapa no admite edición de datos.")
    stage = get_stage(db, project.id, kind)
    check_version(stage, version)
    require_editable(stage)
    try:
        obj = schema.model_validate(data)
    except ValidationError as exc:
        raise ApiError(422, "invalid_content", "El contenido no tiene el formato esperado.", exc.errors(include_url=False)) from exc
    content = copy.deepcopy(stage.content)
    content["data"] = obj.model_dump(mode="json")
    if kind == "architecture" and content.get("selected") and obj.scenario_id not in ARCHITECTURE_IDS:
        raise ApiError(422, "invalid_scenario", "Escenario de arquitectura desconocido.")
    commit_revision(db, stage, content, user, "user", (summary or "Edición manual").strip())
    log_activity(db, project.id, user, "stage.edited", {"kind": kind, "summary": summary})
    db.commit()


# ---------------------------------------------------------------------------
# Etapa 5: arquitectura
# ---------------------------------------------------------------------------


def architecture_evaluate(db: Session, llm: LLMClient, project: Project, user: User, version: int) -> None:
    stages = stages_by_kind(db, project.id)
    stage = stages["architecture"]
    check_version(stage, version)
    require_editable(stage)
    require_upstream_approved(stages, "architecture")
    up = _upstream_artifacts(stages)
    user_prompt = prompts.arch_eval_user_prompt(up["brief"], up["model"], up["api"], up["frontend"])
    begin_generation(db, stage)
    try:
        evaluation: ArchitectureEvaluation = _call(llm, "architecture_eval", prompts.ARCH_EVAL_SYSTEM, user_prompt, ArchitectureEvaluation)
    except LLMError as exc:
        end_generation(db, stage)
        raise llm_failure(exc) from exc
    except Exception:
        end_generation(db, stage)
        raise
    db.refresh(stage)
    if stage.version != version:
        end_generation(db, stage)
        raise ApiError(409, "version_conflict", "La etapa cambió mientras la IA trabajaba. Vuelve a intentarlo.")
    evaluation.scores = [s for s in evaluation.scores if s.scenario_id in ARCHITECTURE_IDS]
    for s in evaluation.scores:
        s.fit = max(1, min(5, s.fit))
    if evaluation.recommended not in ARCHITECTURE_IDS and evaluation.scores:
        evaluation.recommended = max(evaluation.scores, key=lambda s: s.fit).scenario_id
    content = copy.deepcopy(stage.content)
    content["evaluation"] = evaluation.model_dump(mode="json")
    if not content.get("selected"):
        content["selected"] = evaluation.recommended
    commit_revision(db, stage, content, user, "ai", f"Evaluación de arquitecturas (recomendada {evaluation.recommended})")
    stage.generating_since = None
    log_activity(db, project.id, user, "architecture.evaluated", {"recommended": evaluation.recommended})
    db.commit()


def architecture_select(db: Session, project: Project, user: User, scenario_id: str, version: int) -> None:
    if scenario_id not in ARCHITECTURE_IDS:
        raise ApiError(422, "invalid_scenario", f"El escenario {scenario_id} no existe.")
    stage = get_stage(db, project.id, "architecture")
    check_version(stage, version)
    require_editable(stage)
    content = copy.deepcopy(stage.content)
    if content.get("selected") == scenario_id:
        return
    content["selected"] = scenario_id
    if content.get("data") and content["data"].get("scenario_id") != scenario_id:
        content["data"] = None
    commit_revision(db, stage, content, user, "user", f"Escenario seleccionado: {scenario_id}")
    log_activity(db, project.id, user, "architecture.selected", {"scenario_id": scenario_id})
    db.commit()


def architecture_generate(db: Session, llm: LLMClient, project: Project, user: User, version: int, instructions: str | None) -> None:
    instructions = (instructions or "").strip() or None
    stages = stages_by_kind(db, project.id)
    stage = stages["architecture"]
    check_version(stage, version)
    require_editable(stage)
    require_upstream_approved(stages, "architecture")
    selected = stage.content.get("selected")
    scenario = get_architecture(selected) if selected else None
    if scenario is None:
        raise ApiError(409, "no_scenario_selected", "Primero selecciona una de las arquitecturas base.")
    up = _upstream_artifacts(stages)
    current = data_of(stage, ArchitectureSpec)
    user_prompt = prompts.arch_spec_user_prompt(
        up["brief"], up["model"], up["api"], up["frontend"], scenario, evaluation_of(stage), current, instructions
    )
    begin_generation(db, stage)
    try:
        spec: ArchitectureSpec = _call(llm, "architecture_spec", prompts.ARCH_SPEC_SYSTEM, user_prompt, ArchitectureSpec)
    except LLMError as exc:
        end_generation(db, stage)
        raise llm_failure(exc) from exc
    except Exception:
        end_generation(db, stage)
        raise
    db.refresh(stage)
    if stage.version != version:
        end_generation(db, stage)
        raise ApiError(409, "version_conflict", "La etapa cambió mientras la IA trabajaba. Vuelve a intentarlo.")
    spec.scenario_id = selected
    content = copy.deepcopy(stage.content)
    content["data"] = spec.model_dump(mode="json")
    content["based_on"] = {u: stages[u].approved_version for u in UPSTREAM["architecture"]}
    summary = f"Cambio pedido a la IA: {instructions}" if instructions else f"Arquitectura {selected} detallada por la IA"
    commit_revision(db, stage, content, user, "ai", summary)
    stage.generating_since = None
    log_activity(db, project.id, user, "stage.generated", {"kind": "architecture", "instructions": instructions})
    db.commit()


# ---------------------------------------------------------------------------
# Aprobación y reapertura
# ---------------------------------------------------------------------------


def required_approvers(db: Session, project: Project) -> list[ProjectMember]:
    """Integrantes que deben aprobar cada etapa: el dueño y los editores (los lectores no aprueban)."""
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id)).all()
    return sorted((m for m in members if m.role in ("owner", "editor")), key=lambda m: (m.role != "owner", m.created_at))


def current_approvals(db: Session, stage: Stage) -> list[StageApproval]:
    """Aprobaciones que cuentan: solo las de la versión vigente de la etapa."""
    return list(
        db.scalars(
            select(StageApproval).where(StageApproval.stage_id == stage.id, StageApproval.version == stage.version).order_by(StageApproval.created_at)
        ).all()
    )


def approvals_view(db: Session, project: Project, stage: Stage) -> dict[str, Any]:
    required = required_approvers(db, project)
    done = {a.user_id: a for a in current_approvals(db, stage)}
    people = [
        {"user": user_ref(m.user), "role": m.role, "approved": m.user_id in done, "approved_at": iso(done[m.user_id].created_at) if m.user_id in done else None}
        for m in required
    ]
    return {"required": len(people), "count": sum(p["approved"] for p in people), "people": people}


def clear_approvals(db: Session, stages: list[Stage]) -> None:
    ids = [s.id for s in stages]
    if ids:
        for a in db.scalars(select(StageApproval).where(StageApproval.stage_id.in_(ids))).all():
            db.delete(a)


def approve_stage(db: Session, project: Project, user: User, kind: str, version: int) -> None:
    """Registra la aprobación del usuario. La etapa se aprueba cuando aprueban todos los que pueden editar."""
    stages = stages_by_kind(db, project.id)
    stage = stages.get(kind) or get_stage(db, project.id, kind)
    check_version(stage, version)
    if stage.status == STAGE_APPROVED:
        raise ApiError(409, "already_approved", "La etapa ya está aprobada.")
    if stage.status == STAGE_LOCKED:
        raise ApiError(409, "stage_locked", f"«{STAGE_LABELS[kind]}» se habilita al aprobar la etapa anterior.")
    if is_generating(stage):
        raise ApiError(409, "generation_in_progress", "La IA está trabajando en esta etapa. Espera a que termine.")
    require_upstream_approved(stages, kind)
    issues, _ = stage_issues(db, project, stages, kind)
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        raise ApiError(409, "stage_not_ready", "La etapa tiene problemas que impiden aprobarla.", {"issues": errors})

    mine = db.scalar(select(StageApproval).where(StageApproval.stage_id == stage.id, StageApproval.user_id == user.id))
    if mine is not None and mine.version == stage.version:
        raise ApiError(409, "already_approved_by_you", "Ya aprobaste esta versión. Falta que aprueben los demás integrantes.")
    if mine is None:
        db.add(StageApproval(stage_id=stage.id, user_id=user.id, version=stage.version))
    else:
        # Aprobó una versión anterior: su aprobación pasa a la versión vigente.
        mine.version = stage.version
        mine.created_at = utcnow()
    db.flush()

    required = {m.user_id for m in required_approvers(db, project)}
    approved = {a.user_id for a in current_approvals(db, stage)}
    pending = required - approved
    log_activity(
        db, project.id, user, "stage.approval_added", {"kind": kind, "version": stage.version, "count": len(required & approved), "required": len(required)}
    )
    if pending:
        db.commit()
        return

    stage.status = STAGE_APPROVED
    stage.approved_by = user.id
    stage.approved_at = utcnow()
    stage.approved_version = stage.version
    idx = STAGE_KINDS.index(kind)
    if idx + 1 < len(STAGE_KINDS):
        nxt = stages[STAGE_KINDS[idx + 1]]
        if nxt.status == STAGE_LOCKED:
            nxt.status = STAGE_IN_PROGRESS
    log_activity(db, project.id, user, "stage.approved", {"kind": kind, "version": stage.version, "approvers": len(required)})
    db.commit()


def withdraw_approval(db: Session, project: Project, user: User, kind: str) -> None:
    """El usuario retira su aprobación de una etapa que todavía no está aprobada por todos."""
    stage = get_stage(db, project.id, kind)
    if stage.status == STAGE_APPROVED:
        raise ApiError(409, "already_approved", "La etapa ya quedó aprobada por todos. Para cambiarla hay que reabrirla.")
    mine = db.scalar(select(StageApproval).where(StageApproval.stage_id == stage.id, StageApproval.user_id == user.id))
    if mine is None or mine.version != stage.version:
        raise ApiError(409, "not_approved_by_you", "No tienes una aprobación vigente en esta etapa.")
    db.delete(mine)
    log_activity(db, project.id, user, "stage.approval_withdrawn", {"kind": kind, "version": stage.version})
    db.commit()


def reopen_stage(db: Session, project: Project, user: User, kind: str, version: int) -> list[str]:
    stages = stages_by_kind(db, project.id)
    stage = stages.get(kind) or get_stage(db, project.id, kind)
    check_version(stage, version)
    if stage.status != STAGE_APPROVED:
        raise ApiError(409, "not_approved", "Solo se puede reabrir una etapa aprobada.")
    stage.status = STAGE_IN_PROGRESS
    stale = []
    for downstream in STAGE_KINDS[STAGE_KINDS.index(kind) + 1 :]:
        s = stages[downstream]
        if s.status in (STAGE_APPROVED, STAGE_IN_PROGRESS):
            s.status = STAGE_STALE
            stale.append(downstream)
    # Al reabrir, todos tienen que volver a aprobar esta etapa y las que quedaron por revisar.
    clear_approvals(db, [stage] + [stages[k] for k in stale])
    log_activity(db, project.id, user, "stage.reopened", {"kind": kind, "stale": stale})
    db.commit()
    return stale


# ---------------------------------------------------------------------------
# Etapa 6: revisión de consistencia
# ---------------------------------------------------------------------------


def run_review(db: Session, llm: LLMClient, project: Project, user: User, version: int) -> None:
    stages = stages_by_kind(db, project.id)
    stage = stages["review"]
    check_version(stage, version)
    require_editable(stage)
    require_upstream_approved(stages, "review")

    automatic_errors: list[dict] = []
    warnings: list[dict] = []
    for kind in STAGE_KINDS[:-1]:
        issues, _ = stage_issues(db, project, stages, kind)
        for i in issues:
            entry = {**i, "area": AREA_BY_KIND[kind], "stage": kind}
            (automatic_errors if i["severity"] == "error" else warnings).append(entry)
    up = _upstream_artifacts(stages)
    arch = data_of(stages["architecture"], ArchitectureSpec)
    artifacts = {
        "producto": up["brief"].model_dump(mode="json"),
        "modelo_datos": up["model"].model_dump(mode="json") if up["model"] else None,
        "api": up["api"].model_dump(mode="json") if up["api"] else None,
        "pantallas": up["frontend"].model_dump(mode="json") if up["frontend"] else None,
        "arquitectura": arch.model_dump(mode="json") if arch else None,
    }
    user_prompt = prompts.review_user_prompt(artifacts, automatic_errors + warnings)

    begin_generation(db, stage)
    try:
        review: ConsistencyReview = _call(llm, "consistency_review", prompts.REVIEW_SYSTEM, user_prompt, ConsistencyReview)
    except LLMError as exc:
        end_generation(db, stage)
        raise llm_failure(exc) from exc
    except Exception:
        end_generation(db, stage)
        raise
    db.refresh(stage)
    if stage.version != version:
        end_generation(db, stage)
        raise ApiError(409, "version_conflict", "La revisión cambió mientras la IA trabajaba. Vuelve a intentarlo.")

    previous = {f["description"]: f for f in stage.content.get("findings", []) if f["status"] == "accepted"}
    findings = []
    n = 0
    for e in automatic_errors:
        n += 1
        findings.append(
            {
                "id": f"F-{n:02d}",
                "severity": "critica",
                "area": e["area"],
                "description": e["message"],
                "suggestion": f"Corrige en «{STAGE_LABELS[e['stage']]}» (reábrela) y vuelve a ejecutar la revisión.",
                "source": "auto",
                "status": "open",
                "note": "",
                "resolved_by": None,
            }
        )
    for f in review.findings:
        n += 1
        prev = previous.get(f.description)
        findings.append(
            {
                "id": f"F-{n:02d}",
                **f.model_dump(mode="json"),
                "source": "ia",
                "status": prev["status"] if prev else "open",
                "note": prev["note"] if prev else "",
                "resolved_by": prev["resolved_by"] if prev else None,
            }
        )
    content = {
        "findings": findings,
        "warnings": warnings,
        "summary": review.summary,
        "ran_at": iso(utcnow()),
        "based_on": {k: stages[k].version for k in STAGE_KINDS[:-1]},
    }
    commit_revision(db, stage, content, user, "ai", f"Revisión de consistencia: {len(findings)} hallazgo(s)")
    stage.generating_since = None
    log_activity(db, project.id, user, "review.run", {"findings": len(findings)})
    db.commit()


def resolve_finding(db: Session, project: Project, user: User, finding_id: str, resolution: str, note: str, version: int) -> None:
    stage = get_stage(db, project.id, "review")
    check_version(stage, version)
    require_editable(stage)
    content = copy.deepcopy(stage.content)
    finding = next((f for f in content.get("findings", []) if f["id"] == finding_id), None)
    if finding is None:
        raise ApiError(404, "finding_not_found", "El hallazgo no existe.")
    if resolution not in ("fixed", "accepted", "open"):
        raise ApiError(422, "invalid_resolution", "La resolución debe ser fixed, accepted u open.")
    if finding["source"] == "auto" and resolution != "open":
        raise ApiError(409, "auto_finding", "Los problemas automáticos se corrigen en su etapa; luego vuelve a ejecutar la revisión.")
    if resolution == "accepted" and not note.strip():
        raise ApiError(422, "note_required", "Explica por qué se acepta el hallazgo sin cambios.")
    finding["status"] = {"fixed": "resolved", "accepted": "accepted", "open": "open"}[resolution]
    finding["note"] = note.strip()
    finding["resolved_by"] = user.name if resolution != "open" else None
    commit_revision(db, stage, content, user, "user", f"Hallazgo {finding_id}: {finding['status']}")
    log_activity(db, project.id, user, "review.finding", {"id": finding_id, "status": finding["status"]})
    db.commit()


# ---------------------------------------------------------------------------
# Documentos finales
# ---------------------------------------------------------------------------


def generate_documents(db: Session, project: Project, user: User) -> list[Document]:
    stages = stages_by_kind(db, project.id)
    for kind in STAGE_KINDS:
        if stages[kind].status != STAGE_APPROVED:
            raise ApiError(409, "not_ready", f"Para generar los documentos todas las etapas deben estar aprobadas (falta «{STAGE_LABELS[kind]}»).")
    issues, _ = stage_issues(db, project, stages, "review")
    if has_errors(issues):
        raise ApiError(409, "review_blocking", "La revisión tiene pendientes que impiden generar los documentos.", {"issues": issues})
    up = _upstream_artifacts(stages)
    arch = data_of(stages["architecture"], ArchitectureSpec)
    if not (up["model"] and up["api"] and up["frontend"] and arch):
        raise ApiError(409, "not_ready", "Faltan definiciones para generar los documentos.")
    current = db.scalar(select(func.max(Document.version)).where(Document.project_id == project.id)) or 0
    version = current + 1
    now = utcnow()
    source_versions = {k: stages[k].version for k in STAGE_KINDS}
    product_md = product_spec_markdown(
        project_name=project.name, brief=up["brief"], model=up["model"], api=up["api"], fe=up["frontend"], version=version, generated_at=now
    )
    arch_md = architecture_markdown(
        project_name=project.name,
        brief=up["brief"],
        api=up["api"],
        spec=arch,
        evaluation=evaluation_of(stages["architecture"]),
        version=version,
        generated_at=now,
    )
    docs = [
        Document(project_id=project.id, kind="product_spec", filename=PRODUCT_FILENAME, content=product_md, version=version, source_versions=source_versions, generated_by=user.id),
        Document(project_id=project.id, kind="architecture", filename=ARCHITECTURE_FILENAME, content=arch_md, version=version, source_versions=source_versions, generated_by=user.id),
    ]
    db.add_all(docs)
    log_activity(db, project.id, user, "documents.generated", {"version": version})
    db.commit()
    return docs


EXPORT_FILENAMES = {
    "product": "1-definicion-producto.md",
    "data_model": "2-modelo-datos.md",
    "api": "3-backend-api.md",
    "frontend": "4-pantallas.md",
    "architecture": "5-arquitectura.md",
}


def export_stage(db: Session, project: Project, kind: str) -> dict[str, Any]:
    """Markdown de una etapa para copiarlo a otra IA («Copiar para la IA»)."""
    if kind not in EXPORT_FILENAMES:
        raise ApiError(404, "stage_not_found", "Esta etapa no se exporta por separado.")
    stages = stages_by_kind(db, project.id)
    stage = stages[kind]
    if stage.status == STAGE_LOCKED:
        raise ApiError(409, "stage_locked", f"«{STAGE_LABELS[kind]}» todavía no está habilitada.")
    up = _upstream_artifacts(stages)
    try:
        content = stage_markdown(
            kind=kind,
            project_name=project.name,
            brief=up["brief"],
            model=up["model"],
            api=up["api"],
            fe=up["frontend"],
            spec=data_of(stages["architecture"], ArchitectureSpec),
            evaluation=evaluation_of(stages["architecture"]),
            version=stage.version,
            generated_at=utcnow(),
        )
    except ValueError as exc:
        raise ApiError(409, "nothing_to_export", str(exc)) from exc
    return {"kind": kind, "filename": EXPORT_FILENAMES[kind], "version": stage.version, "status": stage.status, "content": content}
