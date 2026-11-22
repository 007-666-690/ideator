"""Recorrido completo: de la idea a los dos documentos Markdown."""

import io
import zipfile

from tests.conftest import answer_all_open, approve, complete_architecture, create_project, generate, register, stage


def test_full_flow_generates_documents(client):
    register(client, name="Jefe", email="jefe@test.cl")
    pid = create_project(client)["id"]

    # Ronda 1: la IA arma un borrador y hace preguntas (2 bloqueantes)
    s = stage(client, pid, "product")
    assert s["status"] == "in_progress"
    r = client.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]})
    assert r.status_code == 200
    s = r.json()
    open_q = [q for q in s["questions"] if q["status"] == "open"]
    assert len(open_q) == 3
    assert sum(q["blocking"] for q in open_q) == 2
    assert s["can_approve"] is False

    # No se puede aprobar con preguntas bloqueantes abiertas
    r = client.post(f"/api/projects/{pid}/stages/product/approve", json={"version": s["version"]})
    assert r.status_code == 409
    codes = {i["code"] for i in r.json()["error"]["details"]["issues"]}
    assert "product.blocking" in codes

    # No se puede avanzar a la siguiente etapa sin aprobar
    dm = stage(client, pid, "data_model")
    assert dm["status"] == "locked"
    r = client.post(f"/api/projects/{pid}/stages/data_model/generate", json={"version": dm["version"]})
    assert r.status_code == 409

    # Ronda 2: respuestas → definición completa
    s = answer_all_open(client, pid)
    assert all(q["status"] != "open" for q in s["questions"])
    assert all(c["ok"] for c in s["checklist"]), s["checklist"]
    assert s["content"]["brief"]["user_types"][0]["id"] == "U1"
    answered = [q for q in s["questions"] if q["answered_by"]]
    assert answered and answered[0]["answered_by"]["name"] == "Jefe"
    approve(client, pid, "product")

    # Modelo de datos
    dm = generate(client, pid, "data_model")
    assert "erDiagram" in dm["mermaid"]
    assert "CREATE TABLE reservations" in dm["ddl"]
    assert any(r["child"] == "reservations" and r["parent"] == "courts" for r in dm["relationships"])
    assert not [i for i in dm["issues"] if i["severity"] == "error"]
    approve(client, pid, "data_model")

    # API
    api = generate(client, pid, "api")
    assert len(api["content"]["data"]["endpoints"]) == 16
    approve(client, pid, "api")

    # Pantallas
    fe = generate(client, pid, "frontend")
    assert fe["navigation_map"].startswith("flowchart")
    approve(client, pid, "frontend")

    # Arquitectura: evaluar las 5, elegir, detallar
    arch = stage(client, pid, "architecture")
    assert len(arch["scenarios"]) == 5
    r = client.post(f"/api/projects/{pid}/stages/architecture/generate", json={"version": arch["version"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_scenario_selected"
    r = client.post(f"/api/projects/{pid}/architecture/evaluate", json={"version": arch["version"]})
    assert r.status_code == 200
    arch = r.json()
    assert arch["content"]["selected"] == "A1"
    r = client.post(f"/api/projects/{pid}/architecture/select", json={"version": arch["version"], "scenario_id": "A9"})
    assert r.status_code == 422
    arch = generate(client, pid, "architecture")
    assert arch["content"]["data"]["scenario_id"] == "A1"
    approve(client, pid, "architecture")

    # Pruebas y datos: plan funcional trazado a requisitos + datos ficticios, sin IA
    ts = stage(client, pid, "testing")
    r = client.post(f"/api/projects/{pid}/testing/generate", json={"version": ts["version"]})
    assert r.status_code == 200, r.text
    ts = r.json()
    cases = ts["content"]["data"]["cases"]
    req_ids = [q["id"] for q in stage(client, pid, "product")["content"]["brief"]["functional_requirements"]]
    assert all(ts["coverage"][rid] for rid in req_ids)  # cada requisito tiene al menos un caso
    kinds = {c["kind"] for c in cases}
    assert {"positivo", "seguridad", "persistencia"} <= kinds and ("negativo" in kinds or "limite" in kinds)
    assert "-- DATOS FICTICIOS" in ts["seed_sql"] and "INSERT INTO reservations" in ts["seed_sql"]
    assert "@ejemplo.test" in ts["seed_sql"]
    approve(client, pid, "testing")

    # Revisión: los supuestos ya quedaron aceptados al aprobar la definición
    assert all(a["accepted"] for a in stage(client, pid, "product")["content"]["brief"]["assumptions"])
    rv = stage(client, pid, "review")
    r = client.post(f"/api/projects/{pid}/review/run", json={"version": rv["version"]})
    assert r.status_code == 200
    rv = r.json()
    assert rv["content"]["findings"][0]["source"] == "ia"
    assert not any(i["code"] == "review.assumptions" for i in rv["issues"])
    r = client.post(f"/api/projects/{pid}/documents")
    assert r.status_code == 409  # la revisión todavía no está aprobada
    assert not [i for i in rv["issues"] if i["severity"] == "error"], rv["issues"]

    # Hallazgo de la IA aceptado con justificación
    fid = rv["content"]["findings"][0]["id"]
    r = client.post(f"/api/projects/{pid}/review/findings/{fid}", json={"version": rv["version"], "resolution": "accepted", "note": ""})
    assert r.status_code == 422
    r = client.post(f"/api/projects/{pid}/review/findings/{fid}", json={"version": rv["version"], "resolution": "accepted", "note": "Se resolverá en la implementación"})
    assert r.status_code == 200
    approve(client, pid, "review")

    # Documentos
    r = client.post(f"/api/projects/{pid}/documents")
    assert r.status_code == 201
    docs = {d["kind"]: d for d in r.json()}
    spec = docs["product_spec"]["content"]
    arch_md = docs["architecture"]["content"]
    assert docs["product_spec"]["filename"] == "especificacion-producto.md"
    for expected in ("## 0. Instrucciones", "RF-03", "RN-02", "CB-06", "```mermaid", "erDiagram", "CREATE TABLE court_blocks", "EP-08 · `POST /api/v1/reservations`", "PA-04", "Supuestos aceptados", "S-01", "## 17. Plan de pruebas funcionales", "PF-01", "## 18. Datos sintéticos", "INSERT INTO"):
        assert expected in spec, expected
    for expected in ("A1 · Monolito modular en Python", "DATABASE_URL", "Single Sign-On", "sequenceDiagram", "401", "403", "Checklist de verificación"):
        assert expected in arch_md, expected
    assert "A5" in arch_md  # alternativas evaluadas

    listing = client.get(f"/api/projects/{pid}/documents").json()
    assert len(listing) == 2
    r = client.get(f"/api/projects/{pid}/documents/{listing[0]['id']}/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    r = client.get(f"/api/projects/{pid}/documents/latest.zip")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert sorted(names) == ["arquitectura.md", "especificacion-producto.md"]

    # Historial de versiones con autor y origen
    revisions = client.get(f"/api/projects/{pid}/revisions").json()
    assert {r["source"] for r in revisions} == {"ai", "user", "system"}
    project = client.get(f"/api/projects/{pid}").json()
    assert project["current_stage"] == "documents"
    assert project["documents"] == 2


def test_delegated_answers_and_free_message(client):
    register(client)
    pid = create_project(client)["id"]
    s = stage(client, pid, "product")
    client.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]})
    s = answer_all_open(client, pid, delegate=True)
    assert all(q["status"] == "resolved" for q in s["questions"])
    assert s["messages"][-1]["role"] == "assistant"

    # Un mensaje libre también abre una ronda
    r = client.post(f"/api/projects/{pid}/product/turn", json={"version": s["version"], "message": "Agreguen que los socios usan el celular"})
    assert r.status_code == 200
    roles = [m["role"] for m in r.json()["messages"]]
    assert "user" in roles

    # Turno vacío
    s = r.json()
    r = client.post(f"/api/projects/{pid}/product/turn", json={"version": s["version"], "answers": [], "message": "  "})
    assert r.status_code == 422


def test_dismiss_only_non_blocking(client):
    register(client)
    pid = create_project(client)["id"]
    s = stage(client, pid, "product")
    s = client.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]}).json()
    blocking = next(q for q in s["questions"] if q["blocking"])
    optional = next(q for q in s["questions"] if not q["blocking"])
    r = client.post(f"/api/projects/{pid}/questions/{blocking['id']}/dismiss", json={"reason": "no"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "blocking_question"
    r = client.post(f"/api/projects/{pid}/questions/{optional['id']}/dismiss", json={"reason": "Se usa 60 min"})
    assert r.status_code == 200
    assert next(q for q in r.json()["questions"] if q["id"] == optional["id"])["status"] == "dismissed"


def test_change_request_to_ai_and_manual_edit(client):
    register(client)
    pid = create_project(client)["id"]
    complete_architecture(client, pid)
    # Reabrir el modelo de datos deja desactualizadas las etapas siguientes
    dm = stage(client, pid, "data_model")
    r = client.post(f"/api/projects/{pid}/stages/data_model/reopen", json={"version": dm["version"]})
    assert r.status_code == 200
    statuses = {s["kind"]: s["status"] for s in client.get(f"/api/projects/{pid}/stages").json()}
    assert statuses["data_model"] == "in_progress"
    assert statuses["api"] == statuses["frontend"] == statuses["architecture"] == "stale"

    # Pedir un cambio a la IA y luego editar a mano
    dm = generate(client, pid, "data_model", instructions="Agrega un teléfono opcional a users")
    data = dm["content"]["data"]
    data["tables"][0]["columns"].append(
        {"name": "phone", "type": "varchar(20)", "nullable": True, "primary_key": False, "unique": False, "default": None, "foreign_key": None, "description": "Teléfono"}
    )
    r = client.put(f"/api/projects/{pid}/stages/data_model", json={"version": dm["version"], "data": data, "summary": "Teléfono en users"})
    assert r.status_code == 200
    assert "phone" in r.json()["ddl"]

    # Contenido mal formado: 422
    r = client.put(f"/api/projects/{pid}/stages/data_model", json={"version": r.json()["version"], "data": {"tables": "x"}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_content"

    # Un modelo con errores no se puede aprobar
    dm = stage(client, pid, "data_model")
    broken = dm["content"]["data"]
    broken["tables"][3]["columns"][1]["foreign_key"]["table"] = "canchas"
    r = client.put(f"/api/projects/{pid}/stages/data_model", json={"version": dm["version"], "data": broken})
    assert r.status_code == 200
    assert any(i["code"] == "dm.fk_table" for i in r.json()["issues"])
    r = client.post(f"/api/projects/{pid}/stages/data_model/approve", json={"version": r.json()["version"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "stage_not_ready"


def test_exportar_cada_etapa_en_markdown(client):
    from tests.conftest import advance_to_architecture

    register(client, name="Jefe", email="export@test.cl")
    pid = create_project(client)["id"]
    r = client.get(f"/api/projects/{pid}/stages/data_model/markdown")
    assert r.status_code == 409  # bloqueada
    advance_to_architecture(client, pid)
    prod = client.get(f"/api/projects/{pid}/stages/product/markdown").json()
    assert prod["filename"] == "1-definicion-producto.md"
    assert "Definición del producto" in prod["content"] and "## 9. Modelo de datos" not in prod["content"]
    dm = client.get(f"/api/projects/{pid}/stages/data_model/markdown").json()["content"]
    assert "## 9. Modelo de datos" in dm and "CREATE TABLE" in dm
    api_md = client.get(f"/api/projects/{pid}/stages/api/markdown").json()["content"]
    assert "## 10. API del backend" in api_md
    fe_md = client.get(f"/api/projects/{pid}/stages/frontend/markdown").json()["content"]
    assert "## 11. Interfaz" in fe_md
    r = client.get(f"/api/projects/{pid}/stages/architecture/markdown")
    assert r.status_code == 409  # todavía sin detallar
    assert client.get(f"/api/projects/{pid}/stages/review/markdown").status_code == 404
