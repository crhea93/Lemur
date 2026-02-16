#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_run (
  run_id BIGINT NOT NULL AUTO_INCREMENT,
  cluster_name VARCHAR(128) NOT NULL,
  obsids_csv TEXT NOT NULL,
  redshift_override DOUBLE DEFAULT NULL,
  status ENUM('queued','downloading','processing','completed','failed') NOT NULL DEFAULT 'queued',
  input_csv_row_hash CHAR(64) NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  started_at DATETIME DEFAULT NULL,
  finished_at DATETIME DEFAULT NULL,
  error_text TEXT DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (run_id),
  UNIQUE KEY uniq_cluster_hash (cluster_name, input_csv_row_hash)
)
"""


CREATE_OBSID_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_run_obsid (
  run_id BIGINT NOT NULL,
  obsid INT NOT NULL,
  download_status ENUM('pending','done','failed') NOT NULL DEFAULT 'pending',
  process_status ENUM('pending','done','failed') NOT NULL DEFAULT 'pending',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (run_id, obsid),
  KEY idx_pipeline_run_obsid_run_id (run_id),
  CONSTRAINT fk_pipeline_run_obsid_run_id
    FOREIGN KEY (run_id) REFERENCES pipeline_run(run_id)
    ON DELETE CASCADE
)
"""


def parse_input_file(path):
    values = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()
    return values


def sanitize_name(name):
    return re.sub(r"[^A-Za-z0-9+_-]", "", name.strip())


def connect(args):
    password = args.db_password or os.environ.get("DB_PASSWORD")
    return mysql.connector.connect(
        host=args.db_host,
        user=args.db_user,
        passwd=password,
        database=args.db_name,
    )


def ensure_tables(cur):
    cur.execute(CREATE_TABLE_SQL)
    cur.execute(CREATE_OBSID_TABLE_SQL)


def claim_next_run(db, include_failed):
    cur = db.cursor(dictionary=True)
    db.start_transaction()
    try:
        statuses = ("queued", "failed") if include_failed else ("queued",)
        placeholders = ",".join(["%s"] * len(statuses))
        cur.execute(
            f"""
            SELECT run_id, cluster_name, obsids_csv, redshift_override, status
            FROM pipeline_run
            WHERE status IN ({placeholders})
            ORDER BY run_id ASC
            LIMIT 1
            FOR UPDATE
            """,
            statuses,
        )
        row = cur.fetchone()
        if not row:
            db.commit()
            cur.close()
            return None

        cur.execute(
            """
            UPDATE pipeline_run
            SET status='downloading',
                started_at=COALESCE(started_at, UTC_TIMESTAMP()),
                finished_at=NULL,
                error_text=NULL,
                attempts=attempts+1
            WHERE run_id=%s
            """,
            (row["run_id"],),
        )
        db.commit()
        cur.close()
        return row
    except Exception:
        db.rollback()
        cur.close()
        raise


def get_obsids(db, run_id):
    cur = db.cursor()
    cur.execute(
        "SELECT obsid FROM pipeline_run_obsid WHERE run_id=%s ORDER BY obsid",
        (run_id,),
    )
    obsids = [str(r[0]) for r in cur.fetchall()]
    cur.close()
    return obsids


def set_obsid_download_status(db, run_id, obsid, status):
    cur = db.cursor()
    cur.execute(
        """
        UPDATE pipeline_run_obsid
        SET download_status=%s
        WHERE run_id=%s AND obsid=%s
        """,
        (status, run_id, int(obsid)),
    )
    db.commit()
    cur.close()


def set_processing_status_for_all_obsids(db, run_id, status):
    cur = db.cursor()
    cur.execute(
        """
        UPDATE pipeline_run_obsid
        SET process_status=%s
        WHERE run_id=%s
        """,
        (status, run_id),
    )
    db.commit()
    cur.close()


def update_run_status(db, run_id, status, error_text=None):
    cur = db.cursor()
    cur.execute(
        """
        UPDATE pipeline_run
        SET status=%s,
            finished_at=CASE WHEN %s IN ('completed','failed') THEN UTC_TIMESTAMP() ELSE finished_at END,
            error_text=%s
        WHERE run_id=%s
        """,
        (status, status, error_text, run_id),
    )
    db.commit()
    cur.close()


def recover_interrupted_runs(db):
    cur = db.cursor()
    cur.execute(
        """
        UPDATE pipeline_run
        SET status='queued',
            error_text='Recovered after interrupted worker process.',
            finished_at=NULL
        WHERE status IN ('downloading','processing')
        """
    )
    recovered = cur.rowcount
    if recovered:
        cur.execute(
            """
            UPDATE pipeline_run_obsid o
            JOIN pipeline_run r ON r.run_id = o.run_id
            SET o.process_status='pending'
            WHERE r.status='queued' AND o.process_status='failed'
            """
        )
    db.commit()
    cur.close()
    return recovered


def download_obsid(obsid, data_root, template, log_handle):
    obsid_dir = data_root / obsid
    if obsid_dir.exists():
        print(
            f"[download] obsid {obsid} already exists at {obsid_dir}", file=log_handle
        )
        return

    cmd_text = template.format(obsid=obsid, dest=str(data_root))
    cmd = shlex.split(cmd_text)
    if not cmd:
        raise RuntimeError("Download command template expanded to empty command.")

    print(f"[download] running: {' '.join(cmd)} (cwd={data_root})", file=log_handle)
    subprocess.run(
        cmd, cwd=str(data_root), check=True, stdout=log_handle, stderr=log_handle
    )


def run_pipeline(repo_root, defaults, cluster_name, obsids, redshift, log_handle):
    cmd = [
        sys.executable,
        str(repo_root / "Pipeline" / "pipeline.py"),
        "--cluster",
        cluster_name,
        "--obsids",
        ",".join(obsids),
        "--defaults",
        str(defaults),
    ]
    if redshift is not None:
        cmd.extend(["--redshift", str(redshift)])

    print(f"[pipeline] running: {' '.join(cmd)}", file=log_handle)
    subprocess.run(
        cmd, cwd=str(repo_root), check=True, stdout=log_handle, stderr=log_handle
    )


def process_one_run(args, db, run_row, defaults_values):
    run_id = run_row["run_id"]
    cluster = run_row["cluster_name"]
    redshift = run_row["redshift_override"]
    obsids = get_obsids(db, run_id)
    if not obsids:
        raise RuntimeError(f"run_id={run_id} has no obsids in pipeline_run_obsid.")

    repo_root = Path(__file__).resolve().parents[2]
    runs_root = Path(args.runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs_root / f"{run_id}_{sanitize_name(cluster)}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "runner.log"

    meta = {
        "run_id": run_id,
        "cluster": cluster,
        "obsids": obsids,
        "redshift_override": redshift,
        "claimed_at_utc": timestamp,
    }
    (run_dir / "run.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    data_root = Path(defaults_values["home_dir"]).expanduser()
    if not data_root.exists():
        raise RuntimeError(f"home_dir does not exist: {data_root}")

    with open(log_path, "a", encoding="utf-8") as log_handle:
        print(
            f"[run] run_id={run_id} cluster={cluster} obsids={','.join(obsids)}",
            file=log_handle,
        )

        if not args.skip_download:
            for obsid in obsids:
                try:
                    download_obsid(
                        obsid, data_root, args.download_cmd_template, log_handle
                    )
                    set_obsid_download_status(db, run_id, obsid, "done")
                except Exception:
                    set_obsid_download_status(db, run_id, obsid, "failed")
                    raise
        else:
            for obsid in obsids:
                set_obsid_download_status(db, run_id, obsid, "done")

        update_run_status(db, run_id, "processing")
        run_pipeline(repo_root, args.defaults, cluster, obsids, redshift, log_handle)
        set_processing_status_for_all_obsids(db, run_id, "done")
        update_run_status(db, run_id, "completed")

    print(f"Completed run_id={run_id}. Log: {log_path}")


def run(args):
    defaults_values = parse_input_file(args.defaults)
    if "home_dir" not in defaults_values:
        raise RuntimeError(f"'home_dir' missing in defaults file: {args.defaults}")

    db = connect(args)
    cur = db.cursor()
    ensure_tables(cur)
    db.commit()
    cur.close()

    if args.recover_interrupted:
        recovered = recover_interrupted_runs(db)
        if recovered:
            print(f"Recovered interrupted runs back to queued: {recovered}")

    processed = 0
    while True:
        run_row = claim_next_run(db, include_failed=args.retry_failed)
        if not run_row:
            break

        run_id = run_row["run_id"]
        try:
            process_one_run(args, db, run_row, defaults_values)
            processed += 1
        except Exception as exc:
            set_processing_status_for_all_obsids(db, run_id, "failed")
            update_run_status(db, run_id, "failed", error_text=str(exc))
            print(f"Failed run_id={run_id}: {exc}")
            if args.stop_on_error:
                break

        if args.once:
            break

    db.close()
    print(f"Queue runner finished. processed={processed}")


def build_parser():
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Process queued Lemur runs.")
    parser.add_argument(
        "--defaults",
        default=str(repo_root / "inputs" / "template.i"),
        help="Defaults .i file used by Pipeline/pipeline.py.",
    )
    parser.add_argument(
        "--runs-root",
        default=str(repo_root / "Pipeline" / "ops" / "runs"),
        help="Directory for per-run logs and metadata.",
    )
    parser.add_argument(
        "--download-cmd-template",
        default="download_chandra_obsid {obsid}",
        help=(
            "Command template to fetch one ObsID. Supports {obsid} and {dest}. "
            "Example: 'download_chandra_obsid {obsid} --output-dir {dest}'."
        ),
    )
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--recover-interrupted",
        action="store_true",
        help="Requeue runs left in downloading/processing by an interrupted worker.",
    )
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument(
        "--once", action="store_true", help="Process at most one queued run."
    )
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-user", default="carterrhea")
    parser.add_argument("--db-name", default="carterrhea")
    parser.add_argument(
        "--db-password", help="DB password. Defaults to DB_PASSWORD env var."
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
