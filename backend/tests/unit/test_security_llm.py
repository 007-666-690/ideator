import json
import uuid
from types import SimpleNamespace

import jwt
import pytest

from app.config import Settings
from app.errors import ApiError
from app.ideator.llm import AzureOpenAIClient, LLMBadOutput, LLMUnavailable, extract_json, strict_json_schema
from app.ideator.schemas import ApiSpec, DataModel, ProductTurn
from app.security import LoginThrottle, create_access_token, decode_access_token, hash_password, verify_password

SETTINGS = Settings(secret_key="k" * 40, llm_provider="azure", azure_openai_endpoint="https://x.invalid/openai/v1", azure_openai_api_key="key")


def test_password_hashing():
    h = hash_password("una-clave-larga")
    assert h != "una-clave-larga"
    assert verify_password(h, "una-clave-larga")
    assert not verify_password(h, "otra")
    assert not verify_password(None, "x")
    assert not verify_password("hash-roto", "x")


def test_jwt_roundtrip_and_errors():
    user = SimpleNamespace(id=uuid.uuid4(), name="Cristiano Hola", email="cristiano@example.com")
    token = create_access_token(user, SETTINGS)
    claims = decode_access_token(token, SETTINGS)
    assert claims.user_id == user.id
    # Campos estándar más dos legibles; el token se lee sin la clave, pero no se puede cambiar
    raw = jwt.decode(token, options={"verify_signature": False})
    assert raw["iss"] == "ideator" and raw["aud"] == "ideator-web" and raw["type"] == "access"
    assert raw["sub"] == str(user.id) and raw["name"] == "Cristiano Hola" and raw["email"] == "cristiano@example.com"
    assert raw["exp"] - raw["iat"] == SETTINGS.access_token_minutes * 60
    assert uuid.UUID(raw["jti"]) and raw["jti"] != decode_access_token(create_access_token(user, SETTINGS), SETTINGS).jti
    with pytest.raises(ApiError) as exc:
        decode_access_token(token + "x", SETTINGS)
    assert exc.value.status == 401
    base = {"iss": "ideator", "aud": "ideator-web", "sub": str(user.id), "iat": 1, "jti": "j", "type": "access"}
    expired = jwt.encode({**base, "exp": 1}, SETTINGS.secret_key, algorithm="HS256")
    with pytest.raises(ApiError) as exc:
        decode_access_token(expired, SETTINGS)
    assert exc.value.code == "session_expired"
    for bad in ({"type": "refresh"}, {"aud": "otra-app"}, {"iss": "otro"}):
        forged = jwt.encode({**base, "exp": 9999999999, **bad}, SETTINGS.secret_key, algorithm="HS256")
        with pytest.raises(ApiError):
            decode_access_token(forged, SETTINGS)
    # Cambiar el sub sin la clave rompe la firma
    tampered = jwt.encode({**raw, "sub": str(uuid.uuid4())}, "otra-clave-cualquiera-de-40-caracteres!!", algorithm="HS256")
    with pytest.raises(ApiError) as exc:
        decode_access_token(tampered, SETTINGS)
    assert exc.value.code == "invalid_token"


def test_login_throttle():
    t = LoginThrottle()
    for _ in range(3):
        t.check("k", 3, 60)
        t.fail("k", 60)
    with pytest.raises(ApiError) as exc:
        t.check("k", 3, 60)
    assert exc.value.status == 429
    t.reset("k")
    t.check("k", 3, 60)


@pytest.mark.parametrize("model", [ProductTurn, DataModel, ApiSpec])
def test_strict_schema(model):
    schema = strict_json_schema(model)

    def walk(node):
        if isinstance(node, list):
            for v in node:
                walk(v)
            return
        if "$ref" in node:
            assert list(node) == ["$ref"]
        if "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        assert "default" not in node
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for sub in value.values():
                    walk(sub)
            elif key in ("items", "anyOf"):
                walk(value)

    walk(schema)
    json.dumps(schema)


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('Aquí va: {"a": {"b": 2}} listo') == '{"a": {"b": 2}}'


class _FakeCompletions:
    def __init__(self, contents=None, error=None):
        self.contents = list(contents or [])
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        content = self.contents.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content, refusal=None))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def _client(completions):
    c = AzureOpenAIClient(SETTINGS)
    c._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return c


def test_azure_client_sends_strict_schema_and_retries_once():
    from app.ideator import fake

    valid = json.dumps(fake.DATA_MODEL)
    completions = _FakeCompletions(['{"summary": "incompleto"}', valid])
    result = _client(completions).complete(task="data_model", system="s", user="u", schema=DataModel, effort="low")
    assert isinstance(result, DataModel)
    assert len(completions.calls) == 2
    first = completions.calls[0]
    assert first["response_format"]["type"] == "json_schema"
    assert first["response_format"]["json_schema"]["strict"] is True
    assert first["reasoning_effort"] == "low"
    assert "temperature" not in first
    assert "no cumplió el esquema" in completions.calls[1]["messages"][1]["content"]


def test_azure_client_bad_output_twice():
    completions = _FakeCompletions(["no es json", "tampoco"])
    with pytest.raises(LLMBadOutput):
        _client(completions).complete(task="data_model", system="s", user="u", schema=DataModel)


def test_azure_client_maps_connection_errors():
    import httpx
    import openai

    err = openai.APIConnectionError(request=httpx.Request("POST", "https://x.invalid"))
    with pytest.raises(LLMUnavailable):
        _client(_FakeCompletions(error=err)).complete(task="data_model", system="s", user="u", schema=DataModel)


def test_azure_client_requires_configuration():
    with pytest.raises(LLMUnavailable):
        AzureOpenAIClient(Settings(llm_provider="azure", azure_openai_endpoint="", azure_openai_api_key=""))
