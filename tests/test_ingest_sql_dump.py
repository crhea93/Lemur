import sqlite3

from api import ingest_sql_dump as ingest


def test_split_tuples_handles_multiple_groups():
    values = "(1,'A'),(2,'B'),(3,'C')"
    assert ingest.split_tuples(values) == ["1,'A'", "2,'B'", "3,'C'"]


def test_split_fields_handles_commas_inside_quotes():
    tuple_blob = "1,'A,b,c',NULL,3.5"
    assert ingest.split_fields(tuple_blob) == ["1", "A,b,c", "NULL", "3.5"]


def test_parse_value_converts_types():
    assert ingest.parse_value("NULL") is None
    assert ingest.parse_value("") is None
    assert ingest.parse_value("42") == 42
    assert ingest.parse_value("-17") == -17
    assert ingest.parse_value("3.14") == 3.14
    assert ingest.parse_value("1e-3") == 0.001
    assert ingest.parse_value("ClusterA") == "ClusterA"


def test_load_inserts_extracts_rows():
    sql_text = """
    INSERT INTO `Clusters` VALUES
      (1,'Abell133',0.0566,'01:02:03','-01:02:03',10,20,1,2,3),
      (2,'Perseus',0.0179,'04:05:06','-04:05:06',11,21,4,5,6);
    """

    rows = ingest.load_inserts(sql_text, "Clusters")

    assert len(rows) == 2
    assert rows[0][0] == 1
    assert rows[0][1] == "Abell133"
    assert rows[1][1] == "Perseus"


def test_create_schema_creates_expected_tables():
    conn = sqlite3.connect(":memory:")
    try:
        ingest.create_schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"Clusters", "Obsids", "Region"}.issubset(tables)
