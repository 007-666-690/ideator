"""Aprobación en equipo: una etapa avanza solo cuando aprueban todos los que pueden editar."""

from tests.conftest import approve, complete_product, create_project, register, stage


def _team(make_client, *, beto_role="editor", with_viewer=False):
    a, b = make_client(), make_client()
    register(a, name="Ana", email="ana@team.cl")
    register(b, name="Beto", email="beto@team.cl")
    pid = create_project(a)["id"]
    inv = a.post(f"/api/projects/{pid}/invitations", json={"email": "beto@team.cl", "role": beto_role}).json()["id"]
    assert b.post(f"/api/invitations/{inv}/accept").status_code == 200
    c = None
    if with_viewer:
        c = make_client()
        register(c, name="Carla", email="carla@team.cl")
        inv = a.post(f"/api/projects/{pid}/invitations", json={"email": "carla@team.cl", "role": "viewer"}).json()["id"]
        assert c.post(f"/api/invitations/{inv}/accept").status_code == 200
    return a, b, c, pid


def test_la_etapa_espera_a_todos_los_editores(make_client):
    a, b, _c, pid = _team(make_client)
    complete_product(a, pid)  # Ana aprueba
    s = stage(a, pid, "product")
    assert s["status"] == "in_progress"
    assert s["approvals"]["count"] == 1 and s["approvals"]["required"] == 2
    assert [p["approved"] for p in s["approvals"]["people"]] == [True, False]
    assert stage(a, pid, "data_model")["status"] == "locked"

    # Ana no puede aprobar dos veces la misma versión
    r = a.post(f"/api/projects/{pid}/stages/product/approve", json={"version": s["version"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_approved_by_you"

    s = approve(b, pid, "product")
    assert s["status"] == "approved"
    assert s["approvals"]["count"] == 2
    assert stage(a, pid, "data_model")["status"] == "in_progress"

    acts = [x["action"] for x in a.get(f"/api/projects/{pid}/activity").json()]
    assert "stage.approval_added" in acts and "stage.approved" in acts


def test_los_lectores_no_cuentan_ni_pueden_aprobar(make_client):
    a, b, c, pid = _team(make_client, beto_role="viewer")
    complete_product(a, pid)
    s = stage(a, pid, "product")
    assert s["status"] == "approved"  # Beto es lector: basta con Ana
    assert s["approvals"]["required"] == 1


def test_un_cambio_invalida_las_aprobaciones(make_client):
    a, b, _c, pid = _team(make_client)
    complete_product(a, pid)
    s = stage(b, pid, "product")
    # Beto edita la definición antes de aprobar: la aprobación de Ana ya no cuenta
    r = b.put(f"/api/projects/{pid}/stages/product", json={"version": s["version"], "brief": s["content"]["brief"], "summary": "Ajuste de Beto"})
    assert r.status_code == 200
    s = r.json()
    assert s["approvals"]["count"] == 0
    s = approve(b, pid, "product")
    assert s["status"] == "in_progress" and s["approvals"]["count"] == 1
    s = approve(a, pid, "product")
    assert s["status"] == "approved"


def test_retirar_aprobacion_y_reabrir(make_client):
    a, b, _c, pid = _team(make_client)
    complete_product(a, pid)
    r = a.delete(f"/api/projects/{pid}/stages/product/approval")
    assert r.status_code == 200
    assert r.json()["approvals"]["count"] == 0
    r = a.delete(f"/api/projects/{pid}/stages/product/approval")
    assert r.status_code == 409

    approve(a, pid, "product")
    approve(b, pid, "product")
    s = stage(a, pid, "product")
    r = a.post(f"/api/projects/{pid}/stages/product/reopen", json={"version": s["version"]})
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "in_progress"
    assert s["approvals"]["count"] == 0  # al reabrir, todos vuelven a aprobar


def test_equipo_al_crear_el_proyecto(make_client):
    a, b = make_client(), make_client()
    register(a, name="Ana", email="ana@team.cl")
    r = a.post("/api/projects", json={"name": "Asado", "idea": "App para dividir los gastos de un asado", "team_emails": ["Beto@Team.cl", "ana@team.cl", "beto@team.cl"]})
    assert r.status_code == 201
    pid = r.json()["id"]
    invs = a.get(f"/api/projects/{pid}/members").json()["invitations"]
    assert [(i["email"], i["role"]) for i in invs] == [("beto@team.cl", "editor")]
    register(b, name="Beto", email="beto@team.cl")
    mine = b.get("/api/invitations").json()
    assert len(mine) == 1 and mine[0]["project_id"] == pid
    assert a.post("/api/projects", json={"name": "X", "idea": "Idea suficientemente larga", "team_emails": ["no-es-correo"]}).status_code == 422
