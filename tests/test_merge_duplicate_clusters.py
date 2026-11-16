import importlib.util
import sqlite3
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "merge_duplicate_clusters",
    Path(__file__).resolve().parents[1] / "scripts" / "merge_duplicate_clusters.py",
)
assert _spec is not None and _spec.loader is not None
mdc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mdc)


def _db():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE Clusters (ID INTEGER PRIMARY KEY, Name TEXT)")
    con.execute("CREATE TABLE Obsids (ClusterNumber INTEGER, Obsid INTEGER)")
    con.execute("CREATE TABLE Region (idCluster INTEGER, idRegion INTEGER)")
    con.execute(
        "CREATE UNIQUE INDEX idx_obsids_cluster_obsid ON Obsids (ClusterNumber, Obsid)"
    )
    con.executemany(
        "INSERT INTO Clusters VALUES (?, ?)", [(1, "A2142"), (2, "Abell2142")]
    )
    con.executemany(
        "INSERT INTO Obsids VALUES (?, ?)",
        [(1, 1196), (1, 5005), (2, 5005), (2, 23844), (2, 24488)],
    )
    return con


PLAN = [
    {
        "canonical": "Abell2142",
        "survivor": {"id": 1, "name": "A2142"},
        "dropped": [{"id": 2, "name": "Abell2142"}],
    }
]


def test_survivor_takes_over_dropped_obsids():
    con = _db()
    gained = mdc.apply_db(con, PLAN)
    assert gained == {"Abell2142": [23844, 24488]}
    assert con.execute("SELECT ID, Name FROM Clusters").fetchall() == [(1, "Abell2142")]
    obsids = con.execute(
        "SELECT ClusterNumber, Obsid FROM Obsids ORDER BY Obsid"
    ).fetchall()
    assert obsids == [(1, 1196), (1, 5005), (1, 23844), (1, 24488)]


def test_no_gain_reported_when_obsids_already_held():
    con = _db()
    con.execute("DELETE FROM Obsids WHERE Obsid IN (23844, 24488)")
    assert mdc.apply_db(con, PLAN) == {}
