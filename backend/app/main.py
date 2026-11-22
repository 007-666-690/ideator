"""Punto de entrada de la API de Ideator.

Ejecutar en desarrollo:
    uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings, get_settings
from .db import get_engine, init_engine
from .errors import ApiError, register_error_handlers
from .models import Base
from .observability import RequestContextMiddleware, configure_logging, metrics_response
from .routers import auth, documents, members, projects, stages

logger = logging.getLogger("ideator")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = init_engine(settings.database_url)
    Base.metadata.create_all(engine)
    from .db import SessionLocal
    from .ideator.engine import ensure_stages

    with SessionLocal() as db:  # proyectos creados antes de agregar una etapa nueva
        added = ensure_stages(db)
        if added:
            logger.info("Etapas nuevas agregadas a proyectos existentes", extra={"added": added})

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("Ideator iniciado", extra={"environment": settings.environment, "llm": settings.llm_provider})
        yield

    app = FastAPI(
        title="Ideator API",
        version="1.0.0",
        description="Transforma una idea en una especificación de software lista para que otra IA la implemente.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    # El último middleware agregado es el más externo.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="ideator_oauth",
        max_age=600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    for router in (auth.router, projects.router, members.router, stages.router, documents.router):
        app.include_router(router)

    @app.get("/api/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/ready", tags=["ops"])
    def ready() -> JSONResponse:
        checks = {"database": "ok", "llm": "ok" if settings.llm_configured else "not_configured"}
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            checks["database"] = "error"
        status = 200 if all(v == "ok" for v in checks.values()) else 503
        return JSONResponse(status_code=status, content={"status": "ok" if status == 200 else "degraded", "checks": checks})

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return metrics_response()

    dist = Path(settings.frontend_dist) if settings.frontend_dist else None
    if dist and (dist / "index.html").exists():
        index = dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise ApiError(404, "not_found", "Ruta no encontrada.")
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(index)

    return app
