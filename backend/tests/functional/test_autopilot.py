"""Piloto automático: al aprobar una etapa, la IA genera la siguiente sola."""

import time

import pytest

from tests.conftest import answer_all_open, approve, create_project, register, stage


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"autopilot": True})


def _wait(client, pid, kind, key, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        s = stage(client, pid, kind)
        if s["content"].get(key) and not s["generating"]:
            return s
        time.sleep(0.1)
    raise AssertionError(f"{kind} no tuvo {key} a tiempo")


def test_autopilot_chains_generation_after_each_approval(client):
    register(client)
    pid = create_project(client)["id"]
    s = stage(client, pid, "product")
    client.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]})
    answer_all_open(client, pid)
    approve(client, pid, "product")

    dm = _wait(client, pid, "data_model", "data")  # nadie apretó "Proponer modelo de datos"
    assert dm["content"]["data"]["tables"]
    approve(client, pid, "data_model")
    _wait(client, pid, "api", "data")
    approve(client, pid, "api")
    _wait(client, pid, "frontend", "data")
    approve(client, pid, "frontend")

    arch = _wait(client, pid, "architecture", "data")  # evaluó las 5, eligió la recomendada y la detalló
    assert arch["content"]["evaluation"] and arch["content"]["selected"] == arch["content"]["data"]["scenario_id"]
    approve(client, pid, "architecture")
    testing = _wait(client, pid, "testing", "data")  # plan de pruebas y datos ficticios, sin IA
    assert testing["content"]["data"]["cases"] and testing["content"]["data"]["seed"]["tables"]
    assert not [i for i in testing["issues"] if i["severity"] == "error"], testing["issues"]
    approve(client, pid, "testing")
    review = _wait(client, pid, "review", "ran_at")
    assert review["status"] == "in_progress"  # el piloto nunca aprueba por el equipo


def test_autopilot_error_is_visible_and_retryable(client, fake_llm, monkeypatch):
    from app.ideator.llm import LLMUnavailable

    register(client)
    pid = create_project(client)["id"]
    s = stage(client, pid, "product")
    client.post(f"/api/projects/{pid}/product/start", json={"version": s["version"]})
    answer_all_open(client, pid)
    original = fake_llm.complete

    def broken(**kw):
        if kw.get("task") == "data_model":
            raise LLMUnavailable("El modelo de IA está saturado.")
        return original(**kw)

    monkeypatch.setattr(fake_llm, "complete", broken)
    approve(client, pid, "product")
    end = time.time() + 10
    while not stage(client, pid, "data_model")["content"].get("auto_error"):
        assert time.time() < end
        time.sleep(0.1)
    sync = client.get(f"/api/projects/{pid}/sync").json()
    assert "saturado" in sync["stages"]["data_model"]["auto_error"]

    monkeypatch.setattr(fake_llm, "complete", original)
    assert client.post(f"/api/projects/{pid}/autopilot").status_code == 200
    dm = _wait(client, pid, "data_model", "data")
    assert "auto_error" not in dm["content"]
