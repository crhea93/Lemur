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


def test_update_api_db_sqlite_mode_skips_mysqldump(monkeypatch, tmp_path):
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


def test_update_api_db_runs_dump_and_ingest(monkeypatch, tmp_path):
    service = _service()
    sql_dump = tmp_path / "Lemur_DB.sql"
    sqlite_db = tmp_path / "lemur.db"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return None

    monkeypatch.setattr(ds.subprocess, "run", fake_run)
    monkeypatch.setattr(
        service, "restart_api_if_running", lambda _inputs: calls.append(("restart", {}))
    )

    service.update_api_db(
        {
            "update_api": "true",
            "sql_dump_path": str(sql_dump),
            "sqlite_db_path": str(sqlite_db),
        }
    )

    # mysqldump then ingest script then restart check
    assert len(calls) == 3
    dump_cmd, dump_kwargs = calls[0]
    ingest_cmd, _ingest_kwargs = calls[1]
    assert dump_cmd[0] == "mysqldump"
    assert dump_cmd[3] == "127.0.0.1"
    assert dump_kwargs["check"] is True
    assert dump_kwargs["env"]["MYSQL_PWD"] == "pw"
    assert "ingest_sql_dump.py" in ingest_cmd[1]
    assert calls[2][0] == "restart"


def test_update_api_db_handles_mysqldump_missing(monkeypatch, tmp_path):
    service = _service()
    sqlite_db = tmp_path / "lemur.db"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "mysqldump":
            raise FileNotFoundError("missing")
        return None

    monkeypatch.setattr(ds.subprocess, "run", fake_run)
    monkeypatch.setattr(service, "restart_api_if_running", lambda _inputs: None)

    service.update_api_db({"update_api": "true", "sqlite_db_path": str(sqlite_db)})
    assert any("ingest_sql_dump.py" in str(part) for part in calls[1])


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
