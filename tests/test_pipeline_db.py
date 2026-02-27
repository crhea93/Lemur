from pathlib import Path
from typing import Any, cast

import pytest

from Pipeline import db as db_module


class FakeCursor:
    def __init__(self, exists=False):
        self.exists = exists
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (1 if self.exists else 0,)


def test_ensure_schema_noop_when_clusters_table_exists():
    cur = FakeCursor(exists=True)
    db_module.ensure_schema(cur, "mydb", "unused.sql")
    assert len(cur.executed) == 1


def test_ensure_schema_raises_when_sql_missing():
    cur = FakeCursor(exists=False)
    with pytest.raises(RuntimeError, match="SQL dump not found"):
        db_module.ensure_schema(cur, "mydb", "missing.sql")


def test_ensure_schema_executes_only_relevant_schema_statements(tmp_path):
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        """
-- comment
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
LOCK TABLES `Clusters` WRITE;
CREATE TABLE Clusters (ID INT);
INSERT INTO `Clusters` VALUES (1,'A');
UNLOCK TABLES;

CREATE TABLE Obsids (ClusterNumber INT, Obsid INT);
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    cur = FakeCursor(exists=False)

    db_module.ensure_schema(cur, "mydb", str(sql_path))

    # One existence check + two CREATE statements
    assert len(cur.executed) == 3
    executed_sql = [call[0].strip() for call in cur.executed[1:]]
    assert executed_sql == [
        "CREATE TABLE Clusters (ID INT);",
        "CREATE TABLE Obsids (ClusterNumber INT, Obsid INT);",
    ]


def test_connect_db_uses_defaults_and_calls_ensure_schema(monkeypatch):
    calls: dict[str, Any] = {}

    class FakeDB:
        def cursor(self):
            return "cursor-obj"

    def fake_connect(**kwargs):
        calls["connect_kwargs"] = kwargs
        return FakeDB()

    def fake_ensure_schema(cur, db_name, sql_path):
        calls["ensure_schema"] = (cur, db_name, sql_path)

    monkeypatch.setattr(db_module.mysql.connector, "connect", fake_connect)
    monkeypatch.setattr(db_module, "ensure_schema", fake_ensure_schema)

    mydb, mycursor, db_user, db_host, db_name = db_module.connect_db(
        {"db_engine": "mysql"},
        "pw",
    )

    assert mydb.__class__.__name__ == "FakeDB"
    assert mycursor == "cursor-obj"
    assert db_user == "carterrhea"
    assert db_host == "localhost"
    assert db_name == "carterrhea"
    assert calls["connect_kwargs"] == {
        "host": "localhost",
        "user": "carterrhea",
        "passwd": "pw",
        "database": "carterrhea",
    }
    ensure_call = cast(tuple[Any, Any, Any], calls["ensure_schema"])
    assert ensure_call[0] == "cursor-obj"
    assert ensure_call[1] == "carterrhea"
    assert Path(ensure_call[2]).name == "lemur.sql"


def test_connect_db_sqlite_mode_creates_schema(tmp_path):
    db_path = tmp_path / "lemur.db"
    mydb, mycursor, _db_user, db_host, _db_name = db_module.connect_db(
        {"db_engine": "sqlite", "sqlite_db_path": str(db_path)},
        "",
    )
    assert db_host == "sqlite"
    mycursor.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='Clusters'"
    )
    assert mycursor.fetchone()[0] == 1
    mydb.close()
