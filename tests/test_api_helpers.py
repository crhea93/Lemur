import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import app as app_module
from api import db as db_module


class _DummyResponse:
    def __init__(self, text: str):
        self._payload = text.encode("utf-8")
        self.status = 200

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fits_download_url_returns_local_route():
    assert app_module.fits_download_url("Abell 133") == "/api/fits/Abell%20133/download"


def test_ensure_db_raises_when_missing(tmp_path, monkeypatch):
    missing = tmp_path / "missing.db"
    monkeypatch.setattr(app_module, "DB_PATH", missing)
    with pytest.raises(HTTPException) as exc:
        app_module.ensure_db()
    assert exc.value.status_code == 503


def test_resolve_name_parses_sesame_response(monkeypatch):
    payload = "%J 12:00:00 +30:00:00\n%I.0 Abell 133\n%I.1 RXC J0102.8-2152\n"

    def fake_urlopen(*_args, **_kwargs):
        return _DummyResponse(payload)

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
    result = app_module.resolve_name("Abell133")
    assert result["query"] == "Abell133"
    assert "Abell 133" in result["names"]
    assert "RXC J0102.8-2152" in result["names"]


def test_resolve_name_handles_network_error(monkeypatch):
    def fake_urlopen(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
    result = app_module.resolve_name("Abell133")
    assert result["names"] == ["Abell133"]


def test_get_conn_uses_sqlite_row_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    with db_module.get_conn() as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t (id) VALUES (1)")
        row = conn.execute("SELECT id FROM t").fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["id"] == 1
