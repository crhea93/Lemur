import re
import sqlite3
from pathlib import Path


class SQLiteCursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    @staticmethod
    def _normalize_sql(sql):
        # Convert MySQL placeholder style to sqlite3 style.
        return re.sub(r"%s", "?", sql)

    def execute(self, sql, params=None):
        normalized = self._normalize_sql(sql)
        if params is None:
            return self._cursor.execute(normalized)
        return self._cursor.execute(normalized, params)

    def executemany(self, sql, seq_of_params):
        normalized = self._normalize_sql(sql)
        return self._cursor.executemany(normalized, seq_of_params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def nextset(self):
        return None

    def close(self):
        return self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class SQLiteConnectionAdapter:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return SQLiteCursorAdapter(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def ensure_sqlite_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS Clusters (
            ID INTEGER NOT NULL,
            Name TEXT NOT NULL,
            redshift REAL NOT NULL DEFAULT 0,
            RightAsc TEXT,
            Declination TEXT,
            R_cool_3 REAL,
            R_cool_7 REAL,
            CSB_ct REAL,
            CSB_pho REAL,
            csb_flux REAL
        );

        CREATE TABLE IF NOT EXISTS Obsids (
            ClusterNumber INTEGER,
            Obsid INTEGER
        );

        CREATE TABLE IF NOT EXISTS Region (
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

        CREATE TABLE IF NOT EXISTS csb (
            ClusterName TEXT,
            ID INTEGER,
            csb_ct REAL,
            csb_ct_l REAL,
            csb_ct_u REAL,
            csb_pho REAL,
            csb_pho_l REAL,
            csb_pho_u REAL,
            csb_flux REAL,
            csb_flux_l REAL,
            csb_flux_u REAL
        );

        CREATE TABLE IF NOT EXISTS r_cool (
            ID INTEGER,
            ClusterName TEXT,
            R_cool_3 REAL,
            R_cool_3_l REAL,
            R_cool_3_u REAL,
            R_cool_7 REAL,
            R_cool_7_l REAL,
            R_cool_7_u REAL
        );

        CREATE TABLE IF NOT EXISTS cluster_center (
            ID INTEGER,
            ClusterName TEXT NOT NULL,
            center_ra REAL,
            center_dec REAL,
            center_x REAL,
            center_y REAL,
            method TEXT,
            image_path TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS double_beta_fit (
            ID INTEGER,
            ClusterName TEXT NOT NULL,
            norm_1 REAL,
            core_radius_1 REAL,
            beta_1 REAL,
            norm_2 REAL,
            core_radius_2 REAL,
            beta_2 REAL,
            background REAL,
            triple_core_radius_2 REAL,
            center_x REAL,
            center_y REAL,
            image_path TEXT,
            plot_path TEXT,
            max_radius REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_clusters_name ON Clusters (Name);
        CREATE INDEX IF NOT EXISTS idx_clusters_id ON Clusters (ID);
        CREATE INDEX IF NOT EXISTS idx_obsids_cluster ON Obsids (ClusterNumber);
        CREATE INDEX IF NOT EXISTS idx_region_cluster ON Region (idCluster);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_center_cluster_name
            ON cluster_center (ClusterName);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_double_beta_cluster_name
            ON double_beta_fit (ClusterName);
        """
    )
    conn.commit()


def ensure_schema(mycursor, db_name, sql_path):
    # Kept for compatibility with older call sites/tests.
    # For SQLite-only mode we ensure schema via ensure_sqlite_schema(connection).
    return None


def connect_db(inputs, db_password):
    _ = db_password
    db_user = inputs.get("db_user", "sqlite")
    db_name = inputs.get("db_name", "lemur")
    repo_root = Path(__file__).resolve().parent.parent
    sqlite_db_path = Path(
        inputs.get("sqlite_db_path") or (repo_root / "api" / "data" / "lemur.db")
    ).expanduser()
    print(f"Connecting to SQLite Database at {sqlite_db_path}...")
    sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_db_path))
    ensure_sqlite_schema(conn)
    wrapped = SQLiteConnectionAdapter(conn)
    cur = wrapped.cursor()
    print(" Connected to SQLite Database!")
    return wrapped, cur, db_user, "sqlite", db_name
