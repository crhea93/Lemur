from Pipeline import db as db_module


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


def test_sqlite_cursor_adapter_normalizes_percent_s_placeholders(tmp_path):
    db_path = tmp_path / "lemur.db"
    mydb, mycursor, _db_user, _db_host, _db_name = db_module.connect_db(
        {"db_engine": "sqlite", "sqlite_db_path": str(db_path)},
        "",
    )
    mycursor.execute("CREATE TABLE t (v TEXT)")
    mycursor.execute("INSERT INTO t (v) VALUES (%s)", ("ok",))
    mycursor.execute("SELECT v FROM t")
    assert mycursor.fetchone()[0] == "ok"
    mydb.close()


def test_ensure_sqlite_schema_dedupes_obsids_and_blocks_repeats(tmp_path):
    import sqlite3

    import pytest

    conn = sqlite3.connect(tmp_path / "lemur.db")
    conn.execute("CREATE TABLE Obsids (ClusterNumber INTEGER, Obsid INTEGER)")
    conn.executemany(
        "INSERT INTO Obsids VALUES (?, ?)", [(1, 554), (1, 3184), (1, 554), (2, 554)]
    )
    db_module.ensure_sqlite_schema(conn)

    rows = conn.execute("SELECT ClusterNumber, Obsid FROM Obsids ORDER BY rowid").fetchall()
    assert rows == [(1, 554), (1, 3184), (2, 554)]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO Obsids VALUES (1, 554)")
    conn.close()
