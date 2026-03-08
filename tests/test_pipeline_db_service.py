import subprocess
from typing import Any, cast

from Pipeline import db_service as ds


class DummyResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _service():
    return ds.DatabaseService(
        mydb="db",
        mycursor="cursor",
        db_user="user",
        db_password="pw",
        db_host="localhost",
        db_name="lemur",
    )


def test_method_delegates_to_database_helpers(monkeypatch):
    service = _service()
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        ds,
        "add_cluster_db",
        lambda db, cur, c, z: calls.setdefault("cluster", (db, cur, c, z)),
    )
    monkeypatch.setattr(
        ds,
        "add_obsid_db",
        lambda db, cur, c, o: calls.setdefault("obsid", (db, cur, c, o)),
    )
    monkeypatch.setattr(
        ds,
        "add_coord",
        lambda db, cur, c, ra, dec: calls.setdefault("coord", (db, cur, c, ra, dec)),
    )
    monkeypatch.setattr(
        ds,
        "add_r_cool",
        lambda db, cur, cid, c, *a, **k: calls.setdefault(
            "rcool", (db, cur, cid, c, a, k)
        ),
    )
    monkeypatch.setattr(
        ds,
        "add_csb",
        lambda db, cur, cid, c, *a, **k: calls.setdefault(
            "csb", (db, cur, cid, c, a, k)
        ),
    )
    monkeypatch.setattr(
        ds,
        "add_fit_db",
        lambda db, cur, *a, **k: calls.setdefault("fit", (db, cur, a, k)),
    )
    monkeypatch.setattr(
        ds, "get_id", lambda db, cur, c: calls.setdefault("id", (db, cur, c)) or 7
    )

    service.add_cluster("Abell133", 0.0566)
    service.add_obsid("Abell133", 2203)
    service.add_coord("Abell133", 1.0, 2.0)
    service.add_r_cool(1, "Abell133", "x")
    service.add_csb(1, "Abell133", "y")
    service.add_fit("a", b=2)
    service.get_id("Abell133")

    assert calls["cluster"] == ("db", "cursor", "Abell133", 0.0566)
    assert calls["obsid"] == ("db", "cursor", "Abell133", 2203)
    assert calls["coord"] == ("db", "cursor", "Abell133", 1.0, 2.0)
    rcool_call = cast(tuple[Any, ...], calls["rcool"])
    csb_call = cast(tuple[Any, ...], calls["csb"])
    fit_call = cast(tuple[Any, ...], calls["fit"])
    assert rcool_call[2:4] == (1, "Abell133")
    assert csb_call[2:4] == (1, "Abell133")
    assert fit_call[2] == ("a",)
    assert calls["id"] == ("db", "cursor", "Abell133")


def test_update_api_db_noop_when_disabled(monkeypatch):
    service = _service()
    called = {"run": 0}
    monkeypatch.setattr(
        ds.subprocess,
        "run",
        lambda *a, **k: called.__setitem__("run", called["run"] + 1),
    )
    service.update_api_db({"update_api": "false"})
    assert called["run"] == 0


def test_update_api_db_sqlite_mode_avoids_subprocess_calls(monkeypatch, tmp_path):
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"sqlite-bytes")

    service = ds.DatabaseService(
        mydb="db",
        mycursor="cursor",
        db_user="user",
        db_password="pw",
        db_host="sqlite",
        db_name="lemur",
    )
    called = {"run": 0}
    monkeypatch.setattr(
        ds.subprocess,
        "run",
        lambda *_a, **_k: called.__setitem__("run", called["run"] + 1),
    )
    monkeypatch.setattr(service, "restart_api_if_running", lambda _inputs: None)

    service.update_api_db(
        {
            "update_api": "true",
            "sqlite_db_path": str(source_db),
        }
    )

    assert called["run"] == 0


def test_restart_api_if_running_noop_when_disabled():
    service = _service()
    service.restart_api_if_running({"api_restart": "false"})


def test_restart_api_if_running_skips_on_health_failure(monkeypatch):
    service = _service()
    monkeypatch.setattr(
        ds.urllib.request, "urlopen", lambda *a, **k: DummyResponse(status=500)
    )
    called = {"run": 0}
    monkeypatch.setattr(
        ds.subprocess,
        "run",
        lambda *a, **k: called.__setitem__("run", called["run"] + 1),
    )
    service.restart_api_if_running(
        {"api_restart": "true", "api_restart_cmd": "echo hi"}
    )
    assert called["run"] == 0


def test_restart_api_if_running_handles_unreachable_health(monkeypatch):
    service = _service()
    monkeypatch.setattr(
        ds.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("down")),
    )
    service.restart_api_if_running(
        {"api_restart": "true", "api_restart_cmd": "echo hi"}
    )


def test_restart_api_if_running_runs_restart_command(monkeypatch):
    service = _service()
    monkeypatch.setattr(
        ds.urllib.request, "urlopen", lambda *a, **k: DummyResponse(status=200)
    )
    calls = []
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    service.restart_api_if_running(
        {"api_restart": "true", "api_restart_cmd": "echo hi"}
    )
    assert calls
    assert calls[0][1]["shell"] is True
    assert calls[0][1]["check"] is True


def test_restart_api_if_running_handles_restart_failure(monkeypatch):
    service = _service()
    monkeypatch.setattr(
        ds.urllib.request, "urlopen", lambda *a, **k: DummyResponse(status=200)
    )

    def raise_called(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "echo hi")

    monkeypatch.setattr(ds.subprocess, "run", raise_called)
    service.restart_api_if_running(
        {"api_restart": "true", "api_restart_cmd": "echo hi"}
    )
