"""Cliente de Vertex AI: firma el JWT de la cuenta de servicio y renueva el token."""

import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.ideator import llm


@pytest.fixture
def key_file(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    path = tmp_path / "vertex-key.json"
    path.write_text(json.dumps({"type": "service_account", "project_id": "ideator-test", "client_email": "plano@ideator-test.iam.gserviceaccount.com", "private_key": pem}))
    return path, key.public_key()


def test_vertex_builds_endpoint_and_token(key_file, monkeypatch):
    path, public_key = key_file
    calls = []

    class Resp:
        status_code = 200

        def json(self):
            return {"access_token": "tok-123", "expires_in": 3600}

    def fake_post(url, data, timeout):
        claims = jwt.decode(data["assertion"], public_key, algorithms=["RS256"], audience=llm.VertexClient.TOKEN_URL)
        calls.append(claims)
        return Resp()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    client = llm.VertexClient(Settings(llm_provider="vertex", vertex_credentials_file=str(path), gemini_model="gemini-3.8-flash"))
    assert client.model == "google/gemini-3.8-flash"
    assert client.fallback_model.startswith("google/")
    assert "projects/ideator-test/locations/global/endpoints/openapi" in str(client._client.base_url)
    client._ensure_token()
    client._ensure_token()  # el segundo usa el token guardado
    assert len(calls) == 1 and calls[0]["iss"].startswith("plano@")
    assert client._client.api_key == "tok-123"


def test_vertex_missing_file_is_clear(tmp_path):
    with pytest.raises(llm.LLMUnavailable, match="cuenta de servicio"):
        llm.VertexClient(Settings(llm_provider="vertex", vertex_credentials_file=str(tmp_path / "no.json")))
