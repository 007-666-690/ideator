"""Miembros e invitaciones. Solo el dueño invita, cambia roles o quita miembros."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ProjectAccess, get_current_user, owner_access, viewer_access
from ..errors import ApiError
from ..ideator.engine import iso, log_activity, user_ref
from ..models import Invitation, ProjectMember, User, utcnow

router = APIRouter(prefix="/api", tags=["members"])


class InvitationIn(BaseModel):
    email: EmailStr
    role: Literal["editor", "viewer"]


class RoleIn(BaseModel):
    role: Literal["editor", "viewer"]


def invitation_out(inv: Invitation) -> dict[str, Any]:
    return {
        "id": str(inv.id),
        "project_id": str(inv.project_id),
        "project_name": inv.project.name if inv.project else None,
        "email": inv.email,
        "role": inv.role,
        "status": inv.status,
        "invited_by": user_ref(inv.inviter),
        "created_at": iso(inv.created_at),
    }


@router.get("/projects/{project_id}/members")
def list_members(access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    members = db.scalars(
        select(ProjectMember).where(ProjectMember.project_id == access.project.id).order_by(ProjectMember.created_at)
    ).all()
    invitations = db.scalars(
        select(Invitation).where(Invitation.project_id == access.project.id, Invitation.status == "pending").order_by(Invitation.created_at)
    ).all()
    return {
        "members": [{"user": user_ref(m.user), "role": m.role, "added_at": iso(m.created_at)} for m in members],
        "invitations": [invitation_out(i) for i in invitations],
    }


@router.post("/projects/{project_id}/invitations", status_code=201)
def invite(body: InvitationIn, access: ProjectAccess = Depends(owner_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    email = body.email.lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None and db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == access.project.id, ProjectMember.user_id == existing_user.id)
    ):
        raise ApiError(409, "already_member", "Esa persona ya es miembro del proyecto.")
    if db.scalar(
        select(Invitation).where(Invitation.project_id == access.project.id, Invitation.email == email, Invitation.status == "pending")
    ):
        raise ApiError(409, "already_invited", "Ya hay una invitación pendiente para ese correo.")
    inv = Invitation(project_id=access.project.id, email=email, role=body.role, invited_by=access.user.id)
    db.add(inv)
    log_activity(db, access.project.id, access.user, "member.invited", {"email": email, "role": body.role})
    db.commit()
    db.refresh(inv)
    return invitation_out(inv)


@router.delete("/projects/{project_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: uuid.UUID, access: ProjectAccess = Depends(owner_access), db: Session = Depends(get_db)) -> Response:
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.project_id != access.project.id:
        raise ApiError(404, "invitation_not_found", "La invitación no existe.")
    if inv.status != "pending":
        raise ApiError(409, "invitation_closed", "La invitación ya no está pendiente.")
    inv.status = "revoked"
    inv.responded_at = utcnow()
    log_activity(db, access.project.id, access.user, "invitation.revoked", {"email": inv.email})
    db.commit()
    return Response(status_code=204)


@router.patch("/projects/{project_id}/members/{user_id}")
def change_role(user_id: uuid.UUID, body: RoleIn, access: ProjectAccess = Depends(owner_access), db: Session = Depends(get_db)) -> dict[str, Any]:
    member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == access.project.id, ProjectMember.user_id == user_id))
    if member is None:
        raise ApiError(404, "member_not_found", "Esa persona no es miembro del proyecto.")
    if member.role == "owner":
        raise ApiError(409, "owner_role", "El rol del dueño no se puede cambiar.")
    member.role = body.role
    log_activity(db, access.project.id, access.user, "member.role_changed", {"user": member.user.name, "role": body.role})
    db.commit()
    return {"user": user_ref(member.user), "role": member.role, "added_at": iso(member.created_at)}


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, access: ProjectAccess = Depends(viewer_access), db: Session = Depends(get_db)) -> Response:
    is_self = user_id == access.user.id
    if not is_self and access.role != "owner":
        raise ApiError(403, "insufficient_role", "Solo el dueño puede quitar miembros.")
    member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == access.project.id, ProjectMember.user_id == user_id))
    if member is None:
        raise ApiError(404, "member_not_found", "Esa persona no es miembro del proyecto.")
    if member.role == "owner":
        raise ApiError(409, "owner_cannot_leave", "El dueño no puede salir ni ser quitado del proyecto.")
    name = member.user.name
    db.delete(member)
    log_activity(db, access.project.id, access.user, "member.left" if is_self else "member.removed", {"user": name})
    db.commit()
    return Response(status_code=204)


@router.get("/invitations")
def my_invitations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Invitation).where(Invitation.email == user.email, Invitation.status == "pending").order_by(Invitation.created_at)).all()
    return [invitation_out(i) for i in rows]


def _my_pending_invitation(db: Session, invitation_id: uuid.UUID, user: User) -> Invitation:
    inv = db.get(Invitation, invitation_id)
    # Una invitación ajena responde 404: no se revela que existe.
    if inv is None or inv.email != user.email:
        raise ApiError(404, "invitation_not_found", "La invitación no existe.")
    if inv.status != "pending":
        raise ApiError(409, "invitation_closed", "La invitación ya no está pendiente.")
    return inv


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(invitation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    inv = _my_pending_invitation(db, invitation_id, user)
    exists = db.scalar(select(ProjectMember).where(ProjectMember.project_id == inv.project_id, ProjectMember.user_id == user.id))
    if exists is None:
        db.add(ProjectMember(project_id=inv.project_id, user_id=user.id, role=inv.role, added_by=inv.invited_by))
    inv.status = "accepted"
    inv.responded_at = utcnow()
    log_activity(db, inv.project_id, user, "invitation.accepted", {"role": inv.role})
    db.commit()
    return {"project_id": str(inv.project_id), "role": inv.role}


@router.post("/invitations/{invitation_id}/decline", status_code=204)
def decline_invitation(invitation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    inv = _my_pending_invitation(db, invitation_id, user)
    inv.status = "declined"
    inv.responded_at = utcnow()
    log_activity(db, inv.project_id, user, "invitation.declined")
    db.commit()
    return Response(status_code=204)
