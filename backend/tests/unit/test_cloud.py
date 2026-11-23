"""Modo Cloud Run: respaldo de la base en el bucket, clave de sesión y Vertex sin archivo de llave."""

import sqlite3

from app import cloud
from app.config import Settings
from app.ideator import llm


class FakeBucket:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def download(self, obj):
        return self.objects.get(obj)

    def upload(self, obj, data):
        self.objects[obj] = data


def test_database_is_restored_and_backed_up(tmp_path, monkeypatch):
    fake = FakeBucket()
    monkeypatch.setattr(cloud, "bucket", lambda: fake)
    url = f"sqlite:///{tmp_path}/ideator.db"
    cloud.restore_database(url)  # bucket vacío: no hace nada
    conn = sqlite3.connect(tmp_path / "ideator.db")
    conn.execute("create table t (x int)")
    conn.execute("insert into t values (42)")
    conn.commit()
    conn.close()
    sync = cloud.DatabaseSync(url)
    sync.flush(force=True)
    assert fake.objects["ideator.db"].startswith(b"SQLite format 3")
    (tmp_path / "ideator.db").unlink()
    cloud.restore_database(url)
    assert sqlite3.connect(tmp_path / "ideator.db").execute("select x from t").fetchone() == (42,)


def test_secret_key_generated_once(monkeypatch):
    fake = FakeBucket()
    monkeypatch.setattr(cloud, "bucket", lambda: fake)
    first = cloud.ensure_secret_key("default", "default")
    assert len(first) >= 32 and cloud.ensure_secret_key("default", "default") == first
    assert cloud.ensure_secret_key("x" * 40, "default") == "x" * 40  # una clave configurada manda


def test_vertex_uses_cloud_run_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("K_SERVICE", "plano")
    monkeypatch.setattr(cloud, "metadata_project", lambda: "ideator-515015")
    monkeypatch.setattr(cloud, "metadata_token", lambda: ("tok-meta", 9e12))
    s = Settings(llm_provider="vertex", vertex_credentials_file=str(tmp_path / "no-existe.json"))
    assert s.llm_configured
    client = llm.VertexClient(s)
    assert "projects/ideator-515015/" in str(client._client.base_url)
    client._ensure_token()
    assert client._client.api_key == "tok-meta"
