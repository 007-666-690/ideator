"""Modo nube (Google Cloud Run).

Cloud Run no guarda archivos entre reinicios, así que la base SQLite se respalda en un bucket de Cloud
Storage: se descarga al arrancar y se sube cada pocos segundos si cambió (y al apagarse). Con una sola
instancia (max-instances=1) basta para el uso del curso. La autenticación con Google sale del servidor
de metadatos de Cloud Run: no hay llaves ni contraseñas en el código ni en variables de entorno.
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx

logger = logging.getLogger("ideator.cloud")

METADATA = "http://metadata.google.internal/computeMetadata/v1"
_HEADERS = {"Metadata-Flavor": "Google"}
DB_OBJECT = "ideator.db"
SECRET_OBJECT = "secret-key.txt"
SYNC_SECONDS = 15


def on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE"))


def metadata_token() -> tuple[str, float]:
    r = httpx.get(f"{METADATA}/instance/service-accounts/default/token", headers=_HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data["access_token"], time.time() + int(data.get("expires_in", 3600))


def metadata_project() -> str:
    r = httpx.get(f"{METADATA}/project/project-id", headers=_HEADERS, timeout=10)
    r.raise_for_status()
    return r.text.strip()


class Bucket:
    def __init__(self, name: str) -> None:
        self.name = name
        self._token = ""
        self._exp = 0.0

    def _auth(self) -> dict[str, str]:
        if time.time() > self._exp - 300:
            self._token, self._exp = metadata_token()
        return {"Authorization": f"Bearer {self._token}"}

    def download(self, obj: str) -> bytes | None:
        r = httpx.get(f"https://storage.googleapis.com/storage/v1/b/{self.name}/o/{quote(obj, safe='')}?alt=media", headers=self._auth(), timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def upload(self, obj: str, data: bytes) -> None:
        r = httpx.post(f"https://storage.googleapis.com/upload/storage/v1/b/{self.name}/o",
                       params={"uploadType": "media", "name": obj}, content=data,
                       headers={**self._auth(), "Content-Type": "application/octet-stream"}, timeout=120)
        r.raise_for_status()


def bucket() -> Bucket | None:
    name = os.environ.get("GCS_BUCKET", "").strip()
    return Bucket(name) if name and on_cloud_run() else None


def ensure_secret_key(current: str, default: str) -> str:
    """Clave de firma de sesiones: se genera una vez y se guarda en el bucket (nadie la escribe a mano)."""
    b = bucket()
    if b is None or (current != default and len(current) >= 32):
        return current
    stored = b.download(SECRET_OBJECT)
    if stored:
        return stored.decode().strip()
    key = secrets.token_urlsafe(48)
    b.upload(SECRET_OBJECT, key.encode())
    logger.info("Clave de sesión generada y guardada en el bucket")
    return key


def sqlite_path(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    return Path(database_url[len(prefix):]) if database_url.startswith(prefix) else None


def restore_database(database_url: str) -> None:
    b, path = bucket(), sqlite_path(database_url)
    if b is None or path is None:
        return
    data = b.download(DB_OBJECT)
    if data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("Base restaurada desde el bucket", extra={"bytes": len(data)})


class DatabaseSync:
    """Sube una copia consistente (API de backup de SQLite) cuando la base cambió."""

    def __init__(self, database_url: str) -> None:
        self.bucket, self.path = bucket(), sqlite_path(database_url)
        self._last = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self.bucket is not None and self.path is not None

    def start(self) -> None:
        if self.enabled:
            self._last = self._mtime()
            self._thread = threading.Thread(target=self._loop, name="db-sync", daemon=True)
            self._thread.start()

    def _mtime(self) -> float:
        times = [p.stat().st_mtime for p in (self.path, Path(f"{self.path}-wal")) if p.exists()]
        return max(times, default=0.0)

    def _loop(self) -> None:
        while not self._stop.wait(SYNC_SECONDS):
            self.flush()

    def flush(self, force: bool = False) -> None:
        if not self.enabled or not self.path.exists():
            return
        with self._lock:
            mtime = self._mtime()
            if not force and mtime <= self._last:
                return
            try:
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = tmp.name
                src, dst = sqlite3.connect(self.path), sqlite3.connect(tmp_path)
                with dst:
                    src.backup(dst)
                src.close()
                dst.close()
                self.bucket.upload(DB_OBJECT, Path(tmp_path).read_bytes())
                self._last = mtime
            except Exception:  # noqa: BLE001 - se reintenta en la próxima vuelta
                logger.exception("No se pudo respaldar la base en el bucket")
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    def stop(self) -> None:
        self._stop.set()
        self.flush(force=True)
