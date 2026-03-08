#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

import mysql.connector
from sqlite_queue_schema import ensure_sqlite_queue_schema


def connect_mysql(args):
    password = args.db_password or os.environ.get("DB_PASSWORD")
    return mysql.connector.connect(
        host=args.db_host,
        user=args.db_user,
        passwd=password,
        database=args.db_name,
    )


def connect_sqlite(path: str) -> sqlite3.Connection:
    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(args):
    mysql_db = connect_mysql(args)
    sqlite_db = connect_sqlite(args.sqlite_db)
    ensure_sqlite_queue_schema(sqlite_db)

    if args.clear_existing:
        sqlite_db.execute("DELETE FROM pipeline_run_obsid")
        sqlite_db.execute("DELETE FROM pipeline_run")
        sqlite_db.commit()

    mysql_cur = mysql_db.cursor(dictionary=True)
    sqlite_cur = sqlite_db.cursor()

    mysql_cur.execute(
        """
        SELECT
          run_id, cluster_name, obsids_csv, redshift_override, status,
          input_csv_row_hash, attempts, started_at, finished_at,
          error_text, created_at, updated_at
        FROM pipeline_run
        ORDER BY run_id
        """
    )
    run_rows = mysql_cur.fetchall()

    for row in run_rows:
        sqlite_cur.execute(
            """
            INSERT OR REPLACE INTO pipeline_run (
              run_id, cluster_name, obsids_csv, redshift_override, status,
              input_csv_row_hash, attempts, started_at, finished_at, error_text,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["run_id"],
                row["cluster_name"],
                row["obsids_csv"],
                row["redshift_override"],
                row["status"],
                row["input_csv_row_hash"],
                row["attempts"],
                None if row["started_at"] is None else str(row["started_at"]),
                None if row["finished_at"] is None else str(row["finished_at"]),
                row["error_text"],
                None if row["created_at"] is None else str(row["created_at"]),
                None if row["updated_at"] is None else str(row["updated_at"]),
            ),
        )

    mysql_cur.execute(
        """
        SELECT run_id, obsid, download_status, process_status, updated_at
        FROM pipeline_run_obsid
        ORDER BY run_id, obsid
        """
    )
    obs_rows = mysql_cur.fetchall()
    for row in obs_rows:
        sqlite_cur.execute(
            """
            INSERT OR REPLACE INTO pipeline_run_obsid (
              run_id, obsid, download_status, process_status, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["run_id"],
                row["obsid"],
                row["download_status"],
                row["process_status"],
                None if row["updated_at"] is None else str(row["updated_at"]),
            ),
        )

    # Ensure autoincrement continues after imported max run_id.
    sqlite_cur.execute("SELECT COALESCE(MAX(run_id), 0) FROM pipeline_run")
    max_run_id = sqlite_cur.fetchone()[0]
    sqlite_cur.execute(
        "INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES('pipeline_run', ?)",
        (max_run_id,),
    )

    sqlite_db.commit()

    sqlite_cur.execute("SELECT COUNT(*) FROM pipeline_run")
    run_count_sqlite = sqlite_cur.fetchone()[0]
    sqlite_cur.execute("SELECT COUNT(*) FROM pipeline_run_obsid")
    obs_count_sqlite = sqlite_cur.fetchone()[0]

    mysql_cur.execute("SELECT COUNT(*) AS c FROM pipeline_run")
    run_count_mysql = mysql_cur.fetchone()["c"]
    mysql_cur.execute("SELECT COUNT(*) AS c FROM pipeline_run_obsid")
    obs_count_mysql = mysql_cur.fetchone()["c"]

    mysql_cur.close()
    mysql_db.close()
    sqlite_cur.close()
    sqlite_db.close()

    print(f"MySQL pipeline_run count:       {run_count_mysql}")
    print(f"SQLite pipeline_run count:      {run_count_sqlite}")
    print(f"MySQL pipeline_run_obsid count: {obs_count_mysql}")
    print(f"SQLite pipeline_run_obsid count:{obs_count_sqlite}")
    print(f"SQLite queue DB written to: {Path(args.sqlite_db).expanduser()}")


def build_parser():
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Migrate historical queue tables from MySQL to SQLite."
    )
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-user", default="carterrhea")
    parser.add_argument("--db-name", default="carterrhea")
    parser.add_argument(
        "--db-password", help="MySQL password. Defaults to DB_PASSWORD env var."
    )
    parser.add_argument(
        "--sqlite-db",
        default=str(
            Path(
                os.getenv(
                    "LEMUR_QUEUE_DB",
                    repo_root / "Pipeline" / "ops" / "pipeline_queue.sqlite3",
                )
            )
        ),
        help="Destination SQLite queue DB path.",
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear destination queue tables before import.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    migrate(args)


if __name__ == "__main__":
    main()
