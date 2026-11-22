from __future__ import annotations

import itertools
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ideator.fake import FakeLLM
from app.ideator.llm import set_llm
from app.main import create_app
from app.security import login_throttle

_counter = itertools.count(1)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        llm_provider="fake",
        secret_key="test-secret-key-test-secret-key-0123456789",
        log_level="WARNING",
        login_max_attempts=5,
        autopilot=False,  # el piloto automático tiene su propia prueba (test_autopilot.py)
    )


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    llm = FakeLLM()
    set_llm(llm)
    yield llm
    set_llm(None)


@pytest.fixture
def app(settings, fake_llm):
    login_throttle._attempts.clear()
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_client(app):
    """Crea clientes independientes (cada uno con su propia cookie de sesión)."""
    clients: list[TestClient] = []

    def factory() -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


def register(client: TestClient, name: str | None = None, email: str | None = None, password: str = "clave-segura-1") -> dict:
    n = next(_counter)
    name = name or f"Usuario {n}"
    email = email or f"usuario{n}@test.cl"
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def create_project(client: TestClient, name: str = "ReservaCancha", idea: str | None = None) -> dict:
    idea = idea or "Una app para que los socios de un club reserven canchas de tenis y pádel sin llamar a la secretaría."
    r = client.post("/api/projects", json={"name": name, "idea": idea})
    assert r.status_code == 201, r.text
    return r.json()


def stage(client: TestClient, project_id: str, kind: str) -> dict:
    r = client.get(f"/api/projects/{project_id}/stages/{kind}")
    assert r.status_code == 200, r.text
    return r.json()


def answer_all_open(client: TestClient, project_id: str, delegate: bool = False) -> dict:
    s = stage(client, project_id, "product")
    answers = []
    for q in s["questions"]:
        if q["status"] == "open":
            text = "[DELEGADO] El equipo delega esta decisión." if delegate else (q["options"][1] if len(q["options"]) > 1 else "Sí")
            answers.append({"question_id": q["id"], "answer": text})
    r = client.post(f"/api/projects/{project_id}/product/turn", json={"version": s["version"], "answers": answers})
    assert r.status_code == 200, r.text
    return r.json()


def approve(client: TestClient, project_id: str, kind: str) -> dict:
    s = stage(client, project_id, kind)
    r = client.post(f"/api/projects/{project_id}/stages/{kind}/approve", json={"version": s["version"]})
    assert r.status_code == 200, r.text
    return r.json()


def generate(client: TestClient, project_id: str, kind: str, instructions: str | None = None) -> dict:
    s = stage(client, project_id, kind)
    r = client.post(f"/api/projects/{project_id}/stages/{kind}/generate", json={"version": s["version"], "instructions": instructions})
    assert r.status_code == 200, r.text
    return r.json()


def complete_product(client: TestClient, project_id: str) -> None:
    s = stage(client, project_id, "product")
    r = client.post(f"/api/projects/{project_id}/product/start", json={"version": s["version"]})
    assert r.status_code == 200, r.text
    answer_all_open(client, project_id)
    approve(client, project_id, "product")


def advance_to_architecture(client: TestClient, project_id: str) -> None:
    complete_product(client, project_id)
    for kind in ("data_model", "api", "frontend"):
        generate(client, project_id, kind)
        approve(client, project_id, kind)


def complete_architecture(client: TestClient, project_id: str) -> None:
    advance_to_architecture(client, project_id)
    s = stage(client, project_id, "architecture")
    r = client.post(f"/api/projects/{project_id}/architecture/evaluate", json={"version": s["version"]})
    assert r.status_code == 200, r.text
    generate(client, project_id, "architecture")
    approve(client, project_id, "architecture")
