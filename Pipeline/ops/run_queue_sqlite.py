#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlite_queue_schema import ensure_sqlite_queue_schema


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def pipeline_safe_cluster_name(name, run_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", name.strip().replace(" ", ""))
    if not safe:
        safe = f"Cluster_{run_id}"
    if len(safe) > 20:
        digest = hashlib.sha1(safe.encode("utf-8")).hexdigest()[:5]
        safe = f"{safe[:14]}_{digest}"
    return safe


def connect_sqlite(args):
    db_path = Path(args.sqlite_db).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def claim_next_run(db, include_failed, max_attempts):
    cur = db.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        if include_failed:
            cur.execute(
                """
                SELECT run_id, cluster_name, obsids_csv, redshift_override, status
                FROM pipeline_run
                WHERE status='queued'
                   OR (status='failed' AND attempts < ?)
                ORDER BY CASE WHEN status='queued' THEN 0 ELSE 1 END, run_id ASC
                LIMIT 1
                """,
                (max_attempts,),
            )
        else:
            cur.execute(
                """
                SELECT run_id, cluster_name, obsids_csv, redshift_override, status
                FROM pipeline_run
                WHERE status='queued'
                ORDER BY run_id ASC
                LIMIT 1
                """
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
                started_at=COALESCE(started_at, ?),
                finished_at=NULL,
                error_text=NULL,
                attempts=attempts+1
            WHERE run_id=?
            """,
            (utc_now(), row["run_id"]),
        )
        db.commit()
        cur.close()
        return dict(row)
    except Exception:
        db.rollback()
        cur.close()
        raise


def get_obsids(db, run_id):
    cur = db.cursor()
    cur.execute(
        "SELECT obsid FROM pipeline_run_obsid WHERE run_id=? ORDER BY obsid",
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
        SET download_status=?
        WHERE run_id=? AND obsid=?
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
        SET process_status=?
        WHERE run_id=?
        """,
        (status, run_id),
    )
    db.commit()
    cur.close()


def update_run_status(db, run_id, status, error_text=None):
    cur = db.cursor()
    finished_at = utc_now() if status in {"completed", "failed"} else None
    cur.execute(
        """
        UPDATE pipeline_run
        SET status=?,
            finished_at=COALESCE(?, finished_at),
            error_text=?
        WHERE run_id=?
        """,
        (status, finished_at, error_text, run_id),
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
            UPDATE pipeline_run_obsid
            SET process_status='pending'
            WHERE process_status='failed'
              AND run_id IN (SELECT run_id FROM pipeline_run WHERE status='queued')
            """
        )
    db.commit()
    cur.close()
    return recovered


def download_obsid(obsid, data_root, template, log_handle):
    obsid_dir = data_root / obsid
    if obsid_dir.exists():
        log_line(f"[download] obsid {obsid} already exists at {obsid_dir}", log_handle)
        return

    cmd_text = template.format(obsid=obsid, dest=str(data_root))
    cmd = shlex.split(cmd_text)
    if not cmd:
        raise RuntimeError("Download command template expanded to empty command.")

    log_line(f"[download] running: {' '.join(cmd)} (cwd={data_root})", log_handle)
    run_command_tee(cmd, str(data_root), log_handle)


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
    log_line(f"[pipeline] running: {' '.join(cmd)}", log_handle)
    run_command_tee(cmd, str(repo_root), log_handle)


def run_command_tee(cmd, cwd, log_handle):
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        log_handle.write(line)
        log_handle.flush()
    return_code = process.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, cmd)


def log_line(message, log_handle=None):
    print(message, flush=True)
    if log_handle is not None:
        log_handle.write(message + "\n")
        log_handle.flush()


def append_failure_record(args, run_row, exc):
    failed_list_path = Path(args.failed_list)
    failed_list_path.parent.mkdir(parents=True, exist_ok=True)
    message = str(exc)
    failure_type = (
        "redshift_lookup_failed"
        if "Unable to resolve redshift" in message
        else "pipeline_failed"
    )
    should_write_header = not failed_list_path.exists()
    with open(failed_list_path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if should_write_header:
            writer.writerow(
                [
                    "failed_at_utc",
                    "run_id",
                    "cluster_name",
                    "obsids_csv",
                    "failure_type",
                    "error_text",
                ]
            )
        writer.writerow(
            [
                utc_now(),
                run_row["run_id"],
                run_row["cluster_name"],
                run_row["obsids_csv"],
                failure_type,
                message,
            ]
        )


def process_one_run(args, db, run_row, defaults_values):
    run_id = run_row["run_id"]
    cluster = run_row["cluster_name"]
    cluster_pipeline = pipeline_safe_cluster_name(cluster, run_id)
    redshift = run_row["redshift_override"]
    redshift_to_use = redshift if redshift is not None else args.default_redshift
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
        log_line(
            f"[run] run_id={run_id} cluster={cluster} obsids={','.join(obsids)}",
            log_handle,
        )
        if cluster_pipeline != cluster:
            log_line(
                f"[run] using pipeline-safe cluster name: {cluster_pipeline}",
                log_handle,
            )
        if redshift is None and redshift_to_use is not None:
            log_line(
                f"[run] using default redshift={redshift_to_use} (no redshift_override in queue)",
                log_handle,
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
        run_pipeline(
            repo_root,
            args.defaults,
            cluster_pipeline,
            obsids,
            redshift_to_use,
            log_handle,
        )
        set_processing_status_for_all_obsids(db, run_id, "done")
        update_run_status(db, run_id, "completed")

    print(f"Completed run_id={run_id}. Log: {log_path}")


def run(args):
    defaults_values = parse_input_file(args.defaults)
    if "home_dir" not in defaults_values:
        raise RuntimeError(f"'home_dir' missing in defaults file: {args.defaults}")

    db = connect_sqlite(args)
    ensure_sqlite_queue_schema(db)

    if args.recover_interrupted:
        recovered = recover_interrupted_runs(db)
        if recovered:
            print(f"Recovered interrupted runs back to queued: {recovered}")

    processed = 0
    while True:
        run_row = claim_next_run(
            db,
            include_failed=args.retry_failed,
            max_attempts=args.max_attempts,
        )
        if not run_row:
            break

        run_id = run_row["run_id"]
        try:
            process_one_run(args, db, run_row, defaults_values)
            processed += 1
        except Exception as exc:
            set_processing_status_for_all_obsids(db, run_id, "failed")
            update_run_status(db, run_id, "failed", error_text=str(exc))
            append_failure_record(args, run_row, exc)
            print(f"Failed run_id={run_id}: {exc}")
            if args.stop_on_error:
                break

        if args.once:
            break

    db.close()
    print(f"Queue runner finished. processed={processed}")


def build_parser():
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Process queued Lemur runs (SQLite).")
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
        help="Path to SQLite queue DB.",
    )
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
    parser.add_argument(
        "--default-redshift",
        type=float,
        help="Fallback redshift for runs without redshift_override (skips online lookup).",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum total attempts per run_id when retrying failed runs.",
    )
    parser.add_argument(
        "--failed-list",
        default=str(repo_root / "Pipeline" / "ops" / "failed_clusters.csv"),
        help="CSV path where failed runs are appended.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
