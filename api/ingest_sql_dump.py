import argparse
import os
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQL = BASE_DIR.parent / "Pipeline" / "Lemur_DB.sql"
DEFAULT_DATA_DIR = Path(
    os.getenv("LEMUR_DATA_DIR", str(BASE_DIR / "data"))
).expanduser()
DEFAULT_DB = Path(
    os.getenv("LEMUR_DB_PATH", str(DEFAULT_DATA_DIR / "lemur.db"))
).expanduser()


def split_tuples(values_blob):
    tuples = []
    depth = 0
    start = None
    for i, ch in enumerate(values_blob):
        if ch == "(" and depth == 0:
            start = i + 1
            depth = 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                tuples.append(values_blob[start:i])
                start = None
    return tuples


def split_fields(tuple_blob):
    fields = []
    buf = []
    in_quote = False
    escape = False
    for ch in tuple_blob:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == "'":
            in_quote = not in_quote
            continue
        if ch == "," and not in_quote:
            fields.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    fields.append("".join(buf).strip())
    return fields


def parse_value(text):
    if text.upper() == "NULL":
        return None
    if text == "":
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d*\.?\d+(e[+-]?\d+)?", text, re.IGNORECASE):
        return float(text)
    return text


def load_inserts(sql_text, table_name):
    pattern = re.compile(
        r"INSERT INTO `" + re.escape(table_name) + r"` VALUES (.*?);",
        re.DOTALL,
    )
    all_rows = []
    for match in pattern.finditer(sql_text):
        values_blob = match.group(1)
        for tuple_blob in split_tuples(values_blob):
            fields = [parse_value(v) for v in split_fields(tuple_blob)]
            all_rows.append(fields)
    return all_rows


def create_schema(conn):
    conn.executescript(
        """
        DROP TABLE IF EXISTS Clusters;
        DROP TABLE IF EXISTS Obsids;
        DROP TABLE IF EXISTS Region;

        CREATE TABLE Clusters (
            ID INTEGER NOT NULL,
            Name TEXT NOT NULL,
            redshift REAL NOT NULL,
            RightAsc TEXT,
            Declination TEXT,
            R_cool_3 REAL,
            R_cool_7 REAL,
            csb_ct REAL,
            csb_pho REAL,
            csb_flux REAL
        );

        CREATE TABLE Obsids (
            ClusterNumber INTEGER,
            Obsid INTEGER
        );

        CREATE TABLE Region (
            idCluster INTEGER NOT NULL,
            idRegion INTEGER NOT NULL,
            Area REAL NOT NULL,
            Temp REAL NOT NULL,
            Temp_min REAL NOT NULL,
            Temp_max REAL NOT NULL,
            Abundance REAL NOT NULL,
            Ab_min REAL NOT NULL,
            Ab_max REAL NOT NULL,
            Norm REAL NOT NULL,
            Norm_min REAL NOT NULL,
            Norm_max REAL NOT NULL,
            Flux REAL NOT NULL,
            Luminosity REAL,
            ReducedChiSquare REAL NOT NULL,
            Agn_bool INTEGER,
            Density REAL,
            Dens_min REAL,
            Dens_max REAL,
            Pressure REAL,
            Press_min REAL,
            Press_max REAL,
            Entropy REAL,
            Entropy_min REAL,
            Entropy_max REAL,
            T_cool REAL,
            T_cool_min REAL,
            T_cool_max REAL,
            AGN INTEGER,
            R_in REAL,
            R_out REAL
        );

        CREATE INDEX idx_clusters_name ON Clusters (Name);
        CREATE INDEX idx_clusters_id ON Clusters (ID);
        CREATE INDEX idx_obsids_cluster ON Obsids (ClusterNumber);
        CREATE INDEX idx_region_cluster ON Region (idCluster);
        """
    )


def main():
    parser = argparse.ArgumentParser(description="Load MySQL dump into SQLite")
    parser.add_argument(
        "--sql",
        default=str(DEFAULT_SQL),
        help="Path to MySQL dump (default: Pipeline/Lemur_DB.sql)",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="Path to SQLite database (default: api/data/lemur.db)",
    )
    args = parser.parse_args()

    sql_path = Path(args.sql)
    db_path = Path(args.db)

    if not sql_path.exists():
        raise SystemExit(f"SQL dump not found: {sql_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        os.remove(db_path)

    sql_text = sql_path.read_text(encoding="utf-8", errors="ignore")
    rows_clusters = load_inserts(sql_text, "Clusters")
    rows_obsids = load_inserts(sql_text, "Obsids")
    rows_region = load_inserts(sql_text, "Region")

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        if rows_clusters:
            conn.executemany(
                """
                INSERT INTO Clusters (
                    ID, Name, redshift, RightAsc, Declination,
                    R_cool_3, R_cool_7, csb_ct, csb_pho, csb_flux
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_clusters,
            )
        if rows_obsids:
            conn.executemany(
                "INSERT INTO Obsids (ClusterNumber, Obsid) VALUES (?, ?)",
                rows_obsids,
            )
        if rows_region:
            conn.executemany(
                """
                INSERT INTO Region (
                    idCluster, idRegion, Area, Temp, Temp_min, Temp_max,
                    Abundance, Ab_min, Ab_max, Norm, Norm_min, Norm_max, Flux,
                    Luminosity, ReducedChiSquare, Agn_bool, Density, Dens_min,
                    Dens_max, Pressure, Press_min, Press_max, Entropy,
                    Entropy_min, Entropy_max, T_cool, T_cool_min, T_cool_max,
                    AGN, R_in, R_out
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows_region,
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Loaded {len(rows_clusters)} clusters")
    print(f"Loaded {len(rows_obsids)} obsids")
    print(f"Loaded {len(rows_region)} regions")
    print(f"SQLite DB created at: {db_path}")


if __name__ == "__main__":
    main()
