"""Documentos finales (Markdown) generados por Ideator."""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ProjectAccess, editor_access, viewer_access
from ..errors import ApiError
from ..ideator.engine import generate_documents, iso, user_ref
from ..models import Document

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])


def doc_out(d: Document, with_content: bool = False) -> dict[str, Any]:
    out = {
        "id": str(d.id),
        "kind": d.kind,
        "filename": d.filename,
        "version": d.version,
        "size": len(d.content.encode("utf-8")),
        "source_versions": d.source_versions,
        "generated_by": user_ref(d.author),
        "created_at": iso(d.created_at),
    }
    if with_content:
        out["content"] = d.content
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "proyecto"


@router.get("")
def list_documents(access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Document).where(Document.project_id == access.project.id).order_by(Document.version.desc(), Document.kind)
    ).all()
    return [doc_out(d) for d in rows]


@router.post("", status_code=201)
def create_documents(access: ProjectAccess = Depends(editor_access), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    docs = generate_documents(db, access.project, access.user)
    return [doc_out(d, with_content=True) for d in docs]


@router.get("/latest.zip")
def download_latest_zip(access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> Response:
    version = db.scalar(select(func.max(Document.version)).where(Document.project_id == access.project.id))
    if not version:
        raise ApiError(404, "no_documents", "Aún no hay documentos generados.")
    docs = db.scalars(select(Document).where(Document.project_id == access.project.id, Document.version == version)).all()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            zf.writestr(d.filename, d.content)
    name = f"{_slug(access.project.name)}-v{version}.zip"
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _get_doc(db: Session, access: ProjectAccess, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.project_id != access.project.id:
        raise ApiError(404, "document_not_found", "El documento no existe.")
    return doc


@router.get("/{document_id}")
def get_document(document_id: uuid.UUID, access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    return doc_out(_get_doc(db, access, document_id), with_content=True)


@router.get("/{document_id}/download")
def download_document(document_id: uuid.UUID, access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> Response:
    doc = _get_doc(db, access, document_id)
    return Response(
        doc.content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )
