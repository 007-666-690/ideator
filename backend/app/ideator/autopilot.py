"""Piloto automático: al aprobarse una etapa, la IA prepara la siguiente sin que nadie apriete un botón.

Con esto el equipo solo conversa en la Definición y después revisa y aprueba; las esperas entre
etapas desaparecen. Corre en un hilo con su propia sesión de base de datos: la petición de
aprobación responde al tiro y el frontend ve el avance con el sondeo de /sync.

Orden: Datos → API → Pantallas → Arquitectura (evaluar las 5, elegir la recomendada y detallarla)
→ Revisión de consistencia. La aprobación sigue siendo del equipo: el piloto nunca aprueba.
"""

from __future__ import annotations

import copy
import logging
import threading
import uuid

from ..config import Settings
from ..db import SessionLocal
from ..errors import ApiError
from ..models import STAGE_APPROVED, STAGE_LOCKED, Project, User
from . import engine
from .llm import LLMError, get_llm

logger = logging.getLogger("ideator.autopilot")
_running: set[uuid.UUID] = set()
_again: set[uuid.UUID] = set()  # aprobaciones que llegaron mientras el piloto aún corría
_lock = threading.Lock()


def _note_error(db, stage, message: str) -> None:
    """Deja el motivo visible en la etapa (sin crear versión) para que el equipo pueda reintentar."""
    db.rollback()
    db.refresh(stage)
    stage.content = {**copy.deepcopy(stage.content), "auto_error": message}
    stage.generating_since = None
    db.commit()


def _step(db, llm, project: Project, user: User) -> bool:
    """Ejecuta el siguiente paso pendiente. Devuelve True si hizo algo (hay que seguir)."""
    stages = engine.stages_by_kind(db, project.id)
    for kind in ("data_model", "api", "frontend", "architecture", "testing", "review"):
        stage = stages[kind]
        if stage.status == STAGE_APPROVED:
            continue
        if stage.status == STAGE_LOCKED or engine.is_generating(stage) or stage.content.get("auto_error"):
            return False
        try:
            fix = stage.content.get("fix_request")
            if fix and kind in ("data_model", "api", "frontend"):
                engine.generate_stage(db, llm, project, user, kind, stage.version, fix)
                return False  # el equipo revisa la corrección y aprueba
            if fix and kind == "architecture":
                engine.architecture_generate(db, llm, project, user, stage.version, fix)
                return False
            if kind in ("data_model", "api", "frontend"):
                if stage.content.get("data"):
                    return False
                engine.generate_stage(db, llm, project, user, kind, stage.version, None)
                return False  # espera la aprobación del equipo
            if kind == "architecture":
                if not stage.content.get("evaluation"):
                    engine.architecture_evaluate(db, llm, project, user, stage.version)
                    return True
                if not stage.content.get("data"):
                    db.refresh(stage)
                    engine.architecture_generate(db, llm, project, user, stage.version, None)
                return False
            if kind == "testing":
                # Sin IA e instantáneo: se rehace siempre que cambió algo de lo que depende.
                if not stage.content.get("data") or engine.outdated(stages, "testing"):
                    engine.generate_testing(db, project, user, stage.version)
                return False
            if not stage.content.get("ran_at") or engine.review_outdated(stages):
                engine.run_review(db, llm, project, user, stage.version)
            return False
        except (ApiError, LLMError) as exc:
            logger.warning("Piloto automático detenido en %s: %s", kind, exc)
            _note_error(db, stage, str(exc))
            return False
    return False


def _run(project_id: uuid.UUID, user_id: uuid.UUID, settings: Settings) -> None:
    db = SessionLocal()
    try:
        project, user = db.get(Project, project_id), db.get(User, user_id)
        if project is None or user is None:
            return
        llm = get_llm(settings)
        while True:
            while _step(db, llm, project, user):
                db.expire_all()
            with _lock:
                if project_id not in _again:
                    _running.discard(project_id)
                    return
                _again.discard(project_id)
            db.expire_all()
    except Exception:  # noqa: BLE001 - un hilo nunca debe botar el servidor
        logger.exception("Error en el piloto automático")
    finally:
        db.close()
        with _lock:
            _running.discard(project_id)
            _again.discard(project_id)


def kick(project_id: uuid.UUID, user_id: uuid.UUID, settings: Settings, wait: bool = False) -> None:
    """Lanza el piloto para el proyecto si no hay otro corriendo. wait=True lo ejecuta en línea (pruebas)."""
    if not settings.autopilot:
        return
    with _lock:
        if project_id in _running:
            _again.add(project_id)  # el hilo que corre volverá a mirar antes de terminar
            return
        _running.add(project_id)
    if wait:
        _run(project_id, user_id, settings)
    else:
        threading.Thread(target=_run, args=(project_id, user_id, settings), daemon=True, name=f"autopilot-{project_id}").start()


def clear_error(db, stage) -> None:
    if stage.content.get("auto_error"):
        content = copy.deepcopy(stage.content)
        content.pop("auto_error", None)
        stage.content = content
        db.commit()
