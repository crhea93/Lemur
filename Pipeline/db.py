from pathlib import Path

import mysql.connector


def ensure_schema(mycursor, db_name, sql_path):
    mycursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = 'Clusters'
        """,
        (db_name,),
    )
    exists = mycursor.fetchone()[0] > 0
    if exists:
        return

    if not sql_path or not Path(sql_path).exists():
        raise RuntimeError(f"SQL dump not found for schema init: {sql_path}")

    statements = []
    current = []
    with open(sql_path, "r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("--"):
                continue
            if line.startswith("/*") or line.startswith("/*!"):
                continue
            upper = line.upper()
            if upper.startswith("LOCK TABLES") or upper.startswith("UNLOCK TABLES"):
                continue
            if upper.startswith("INSERT INTO"):
                continue
            current.append(raw)
            if ";" in raw:
                statements.append("".join(current))
                current = []

    for stmt in statements:
        stmt_clean = stmt.strip()
        if not stmt_clean:
            continue
        mycursor.execute(stmt_clean)


def connect_db(inputs, db_password):
    db_user = inputs.get("db_user", "carterrhea")
    db_host = inputs.get("db_host", "localhost")
    db_name = inputs.get("db_name", "carterrhea")

    print("Connecting to Database...")
    mydb = mysql.connector.connect(
        host=db_host, user=db_user, passwd=db_password, database=db_name
    )
    mycursor = mydb.cursor()
    print(" Connected to Database!")

    sql_dump_path = inputs.get("sql_dump_path") or str(
        Path(__file__).resolve().parent.parent / "lemur.sql"
    )
    ensure_schema(mycursor, db_name, sql_dump_path)

    return mydb, mycursor, db_user, db_host, db_name
