from tests.conftest import register


def test_register_login_logout_me(client):
    user = register(client, name="Ana", email="ana@test.cl")
    assert user["email"] == "ana@test.cl"
    assert user["has_password"] is True
    assert "ideator_session" in client.cookies

    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["name"] == "Ana"

    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    client.cookies.clear()
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"

    r = client.post("/api/auth/login", json={"email": "ANA@test.cl", "password": "clave-segura-1"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_register_duplicate_and_invalid(client):
    register(client, email="dup@test.cl")
    r = client.post("/api/auth/register", json={"email": "dup@test.cl", "name": "X", "password": "otra-clave-1"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_in_use"

    r = client.post("/api/auth/register", json={"email": "no-es-correo", "name": "X", "password": "otra-clave-1"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "corta@test.cl", "name": "X", "password": "123"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_login_wrong_password_and_throttle(client):
    register(client, email="b@test.cl")
    client.cookies.clear()
    for _ in range(5):
        r = client.post("/api/auth/login", json={"email": "b@test.cl", "password": "mala-clave"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "invalid_credentials"
    r = client.post("/api/auth/login", json={"email": "b@test.cl", "password": "clave-segura-1"})
    assert r.status_code == 429


def test_invalid_token_is_401(client):
    client.cookies.set("ideator_session", "token-invalido")
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"
    r = client.get("/api/projects", headers={"Authorization": "Bearer otro-token"})
    assert r.status_code == 401


def test_sso_providers_and_not_configured(client):
    r = client.get("/api/auth/providers")
    assert r.status_code == 200
    ids = {p["id"]: p["enabled"] for p in r.json()}
    assert ids == {"microsoft": False, "google": False}
    r = client.get("/api/auth/sso/microsoft/login", follow_redirects=False)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "sso_not_configured"
    r = client.get("/api/auth/sso/facebook/login", follow_redirects=False)
    assert r.status_code == 404


def test_health_ready_metrics(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    r = client.get("/api/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "ideator_http_requests_total" in r.text
    assert "x-request-id" in {k.lower() for k in client.get("/api/health").headers}


def test_session_explained_and_logout_revokes_copied_token(client):
    register(client, name="Cristiano Hola", email="cristiano@test.cl")
    token = client.cookies.get("ideator_session")
    r = client.get("/api/auth/session")
    assert r.status_code == 200
    data = r.json()
    assert data["storage"]["cookie_name"] == "ideator_session" and data["storage"]["http_only"] is True
    assert data["claims"]["sub"] == data["user"]["id"] and "email" not in data["claims"] and "name" not in data["claims"]
    assert [f["claim"] for f in data["fields"]] == ["iss", "aud", "sub", "iat", "exp", "jti", "type"]
    assert token not in r.text  # el token mismo nunca se devuelve (la cookie es HttpOnly)

    # Alguien copia el token desde DevTools; después el usuario cierra sesión
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "session_revoked"
    assert client.get("/api/auth/session").status_code == 401
