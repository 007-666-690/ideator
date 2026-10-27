"""Colaboración: versiones, conflictos y fallas del modelo de IA."""

from app.ideator.llm import LLMUnavailable, set_llm
from tests.conftest import complete_product, create_project, register, stage


def _team(make_client):
    a, b = make_client(), make_client()
    register(a, name="Ana", email="ana@team.cl")
    register(b, name="Beto", email="beto@team.cl")
    pid = create_project(a)["id"]
    inv = a.post(f"/api/projects/{pid}/invitations", json={"email": "beto@team.cl", "role": "editor"}).json()["id"]
    assert b.post(f"/api/invitations/{inv}/accept").status_code == 200
    return a, b, pid


def test_stale_version_conflict(make_client):
    a, b, pid = _team(make_client)
    complete_product(a, pid)
    s = stage(a, pid, "data_model")
    version = s["version"]
    # Ana genera; Beto intenta guardar con la versión vieja
    r = a.post(f"/api/projects/{pid}/stages/data_model/generate", json={"version": version})
    assert r.status_code == 200
    data = r.json()["content"]["data"]
    r = b.put(f"/api/projects/{pid}/stages/data_model", json={"version": version, "data": data})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "version_conflict"
    assert err["details"]["updated_by"] == "Ana"
    assert err["details"]["current_version"] == version + 1
    # Con la versión vigente sí puede
    r = b.put(f"/api/projects/{pid}/stages/data_model", json={"version": version + 1, "data": data, "summary": "Revisión de Beto"})
    assert r.status_code == 200
    assert r.json()["updated_by"]["name"] == "Beto"


def test_approved_stage_is_read_only(make_client):
    a, _b, pid = _team(make_client)
    complete_product(a, pid)
    s = stage(a, pid, "product")
    r = a.put(f"/api/projects/{pid}/stages/product", json={"version": s["version"], "brief": s["content"]["brief"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "stage_approved"


def test_sync_reports_changes(make_client):
    a, b, pid = _team(make_client)
    before = b.get(f"/api/projects/{pid}/sync").json()
    s = stage(a, pid, "product")
    a.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]})
    after = b.get(f"/api/projects/{pid}/sync").json()
    assert after["last_activity_id"] > before["last_activity_id"]
    assert after["stages"]["product"]["version"] > before["stages"]["product"]["version"]
    assert after["questions"]["open_blocking"] == 2


class _DownLLM:
    name = "down"

    def complete(self, **_kwargs):
        raise LLMUnavailable("No se pudo conectar con el modelo de IA.")


def test_llm_down_keeps_answers(client, fake_llm):
    register(client)
    pid = create_project(client)["id"]
    s = stage(client, pid, "product")
    s = client.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]}).json()
    q = next(q for q in s["questions"] if q["blocking"])

    set_llm(_DownLLM())
    r = client.post(f"/api/projects/{pid}/product/turn", json={"version": s["version"], "answers": [{"question_id": q["id"], "answer": "Socios y administrador"}]})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "llm_unavailable"
    s = stage(client, pid, "product")
    assert s["generating"] is False
    assert next(x for x in s["questions"] if x["id"] == q["id"])["status"] == "answered"
    assert any(i["code"] == "product.pending_answers" for i in s["issues"])

    # Vuelve el modelo: se procesan las respuestas pendientes sin reenviarlas
    set_llm(fake_llm)
    r = client.post(f"/api/projects/{pid}/product/turn", json={"version": s["version"], "answers": []})
    assert r.status_code == 200
    assert next(x for x in r.json()["questions"] if x["id"] == q["id"])["status"] == "resolved"


def test_generation_lock(client):
    register(client)
    pid = create_project(client)["id"]
    complete_product(client, pid)
    from app.db import SessionLocal
    from app.ideator.engine import get_stage
    from app.models import utcnow

    db = SessionLocal()
    st = get_stage(db, __import__("uuid").UUID(pid), "data_model")
    st.generating_since = utcnow()
    db.commit()
    db.close()
    s = stage(client, pid, "data_model")
    assert s["generating"] is True
    r = client.post(f"/api/projects/{pid}/stages/data_model/generate", json={"version": s["version"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "generation_in_progress"
