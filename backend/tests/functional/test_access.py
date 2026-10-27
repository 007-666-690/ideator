"""Privacidad de proyectos y permisos: siempre validados en el backend."""

import uuid

from tests.conftest import create_project, register, stage


def test_project_is_private(make_client):
    owner, other = make_client(), make_client()
    register(owner, email="owner@test.cl")
    register(other, email="other@test.cl")
    project = create_project(owner)
    pid = project["id"]
    assert project["my_role"] == "owner"

    # Otro usuario autenticado: 403 aunque conozca el id
    r = other.get(f"/api/projects/{pid}")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    for path in (f"/api/projects/{pid}/stages/product", f"/api/projects/{pid}/activity", f"/api/projects/{pid}/documents", f"/api/projects/{pid}/questions"):
        assert other.get(path).status_code == 403
    assert other.patch(f"/api/projects/{pid}", json={"name": "Hackeado"}).status_code == 403
    assert other.post(f"/api/projects/{pid}/product/start", json={"version": 1}).status_code == 403

    # No aparece en su listado
    assert other.get("/api/projects").json() == []
    assert [p["id"] for p in owner.get("/api/projects").json()] == [pid]

    # Sin sesión: 401; proyecto inexistente: 404; id mal formado: 422
    anon = make_client()
    assert anon.get(f"/api/projects/{pid}").status_code == 401
    assert owner.get(f"/api/projects/{uuid.uuid4()}").status_code == 404
    assert owner.get("/api/projects/no-es-un-uuid").status_code == 422


def test_invitations_and_roles(make_client):
    owner, editor, viewer, stranger = make_client(), make_client(), make_client(), make_client()
    register(owner, email="o@test.cl")
    register(editor, email="e@test.cl", name="Edu")
    register(viewer, email="v@test.cl", name="Vale")
    register(stranger, email="s@test.cl")
    pid = create_project(owner)["id"]

    r = owner.post(f"/api/projects/{pid}/invitations", json={"email": "E@test.cl", "role": "editor"})
    assert r.status_code == 201
    inv_editor = r.json()["id"]
    assert owner.post(f"/api/projects/{pid}/invitations", json={"email": "e@test.cl", "role": "viewer"}).status_code == 409
    inv_viewer = owner.post(f"/api/projects/{pid}/invitations", json={"email": "v@test.cl", "role": "viewer"}).json()["id"]

    # Solo el invitado ve y acepta su invitación
    assert [i["id"] for i in editor.get("/api/invitations").json()] == [inv_editor]
    assert stranger.post(f"/api/invitations/{inv_editor}/accept").status_code == 404
    assert editor.post(f"/api/invitations/{inv_editor}/accept").status_code == 200
    assert editor.post(f"/api/invitations/{inv_editor}/accept").status_code == 409
    assert viewer.post(f"/api/invitations/{inv_viewer}/accept").status_code == 200

    # El lector puede ver pero no modificar
    assert viewer.get(f"/api/projects/{pid}").json()["my_role"] == "viewer"
    s = stage(viewer, pid, "product")
    r = viewer.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"

    # El editor puede trabajar, pero no invitar
    assert editor.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]}).status_code == 200
    assert editor.post(f"/api/projects/{pid}/invitations", json={"email": "x@test.cl", "role": "viewer"}).status_code == 403

    # Cambiar rol y quitar miembros (solo dueño); el dueño no puede salir
    members = owner.get(f"/api/projects/{pid}/members").json()["members"]
    viewer_id = next(m["user"]["id"] for m in members if m["user"]["email"] == "v@test.cl")
    owner_id = next(m["user"]["id"] for m in members if m["role"] == "owner")
    assert editor.patch(f"/api/projects/{pid}/members/{viewer_id}", json={"role": "editor"}).status_code == 403
    assert owner.patch(f"/api/projects/{pid}/members/{viewer_id}", json={"role": "editor"}).json()["role"] == "editor"
    assert owner.patch(f"/api/projects/{pid}/members/{owner_id}", json={"role": "viewer"}).status_code == 409
    assert owner.delete(f"/api/projects/{pid}/members/{owner_id}").status_code == 409
    assert owner.delete(f"/api/projects/{pid}/members/{viewer_id}").status_code == 204
    assert viewer.get(f"/api/projects/{pid}").status_code == 403

    # Trazabilidad: la actividad registra quién hizo qué
    actions = [(a["action"], a["user"]["email"]) for a in owner.get(f"/api/projects/{pid}/activity").json()]
    assert ("invitation.accepted", "e@test.cl") in actions
    assert ("product.started", "e@test.cl") in actions
    assert ("member.removed", "o@test.cl") in actions


def test_revoke_and_decline(make_client):
    owner, guest = make_client(), make_client()
    register(owner, email="own@test.cl")
    register(guest, email="guest@test.cl")
    pid = create_project(owner)["id"]
    inv = owner.post(f"/api/projects/{pid}/invitations", json={"email": "guest@test.cl", "role": "viewer"}).json()["id"]
    assert owner.delete(f"/api/projects/{pid}/invitations/{inv}").status_code == 204
    assert guest.post(f"/api/invitations/{inv}/accept").status_code == 409
    inv2 = owner.post(f"/api/projects/{pid}/invitations", json={"email": "guest@test.cl", "role": "viewer"}).json()["id"]
    assert guest.post(f"/api/invitations/{inv2}/decline").status_code == 204
    assert guest.get(f"/api/projects/{pid}").status_code == 403


def test_owner_can_delete_project(make_client):
    owner, editor = make_client(), make_client()
    register(owner, email="del@test.cl")
    register(editor, email="del2@test.cl")
    pid = create_project(owner)["id"]
    inv = owner.post(f"/api/projects/{pid}/invitations", json={"email": "del2@test.cl", "role": "editor"}).json()["id"]
    editor.post(f"/api/invitations/{inv}/accept")
    assert editor.delete(f"/api/projects/{pid}").status_code == 403
    assert owner.delete(f"/api/projects/{pid}").status_code == 204
    assert owner.get(f"/api/projects/{pid}").status_code == 404
