#!/usr/bin/env python3
import argparse
import csv
import hashlib
import os
import pickle
import re
from collections import defaultdict

import mysql.connector

CLUSTER_CANDIDATES = (
    "cluster",
    "cluster_name",
    "name",
    "target name",
    "target_name",
)
OBSID_CANDIDATES = (
    "obsid",
    "obs id",
    "obs_id",
    "obsids",
    "obs ids",
    "obs_list",
    "dir_list",
)
REDSHIFT_CANDIDATES = ("redshift", "z")


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


def normalize_header(value):
    return re.sub(r"\s+", " ", value.strip().lower())


def find_column(headers, explicit, candidates):
    if explicit:
        key = normalize_header(explicit)
        if key in headers:
            return key
        raise ValueError(
            f"Requested column '{explicit}' not found. Available: {sorted(headers)}"
        )
    for c in candidates:
        c_norm = normalize_header(c)
        if c_norm in headers:
            return c_norm
    return None


def parse_obsids(value):
    if value is None:
        return []
    return sorted({int(match) for match in re.findall(r"\d+", str(value))})


def parse_redshift(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


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


def ingest_rows(args):
    groups = defaultdict(lambda: {"obsids": set(), "redshift": None})
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=args.delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")
        headers = {normalize_header(h): h for h in reader.fieldnames}
        cluster_key = find_column(headers, args.cluster_col, CLUSTER_CANDIDATES)
        obsid_key = find_column(headers, args.obsid_col, OBSID_CANDIDATES)
        redshift_key = find_column(headers, args.redshift_col, REDSHIFT_CANDIDATES)

        if not cluster_key or not obsid_key:
            raise ValueError(
                "Could not detect cluster/obsid columns. Pass --cluster-col and --obsid-col."
            )

        for row in reader:
            cluster = (row.get(headers[cluster_key]) or "").strip()
            if not cluster:
                continue
            obsids = parse_obsids(row.get(headers[obsid_key]))
            if not obsids:
                continue
            groups[cluster]["obsids"].update(obsids)
            if redshift_key and groups[cluster]["redshift"] is None:
                groups[cluster]["redshift"] = parse_redshift(
                    row.get(headers[redshift_key])
                )

    return groups


def _first_present(dct, keys):
    for key in keys:
        if key in dct and dct[key] is not None and str(dct[key]).strip() != "":
            return dct[key]
    return None


def ingest_pickle(args):
    groups = defaultdict(lambda: {"obsids": set(), "redshift": None})
    with open(args.pickle, "rb") as handle:
        data = pickle.load(handle)

    if not isinstance(data, list):
        raise ValueError("Pickle must contain a list of cluster entries.")

    for idx, entry in enumerate(data, start=1):
        cluster = None
        obsid_raw = None
        redshift_raw = None

        if isinstance(entry, dict):
            cluster = _first_present(
                entry,
                (
                    "cluster",
                    "cluster_name",
                    "name",
                    "target_name",
                    "target name",
                ),
            )
            obsid_raw = _first_present(
                entry, ("obsids", "obsid", "obs_ids", "dir_list", "obs_list")
            )
            redshift_raw = _first_present(entry, ("redshift", "z"))
        elif isinstance(entry, (list, tuple, set)):
            obsid_raw = list(entry)
        else:
            obsid_raw = entry

        obsids = parse_obsids(obsid_raw)
        if not obsids:
            continue

        if not cluster:
            cluster = f"Cluster_{idx:04d}"
        cluster = str(cluster).strip()
        groups[cluster]["obsids"].update(obsids)

        if groups[cluster]["redshift"] is None:
            groups[cluster]["redshift"] = parse_redshift(redshift_raw)

    return groups


def run(args):
    if args.csv:
        grouped = ingest_rows(args)
    else:
        grouped = ingest_pickle(args)

    if not grouped:
        print("No valid rows found in input manifest.")
        return

    db = connect(args)
    cur = db.cursor()
    ensure_tables(cur)

    created = 0
    skipped = 0

    for cluster_name in sorted(grouped):
        obsids = sorted(grouped[cluster_name]["obsids"])
        obsids_csv = ",".join(str(x) for x in obsids)
        redshift = grouped[cluster_name]["redshift"]
        digest = hashlib.sha256(
            f"{cluster_name}|{obsids_csv}".encode("utf-8")
        ).hexdigest()

        cur.execute(
            """
            INSERT INTO pipeline_run
              (cluster_name, obsids_csv, redshift_override, status, input_csv_row_hash)
            VALUES (%s, %s, %s, 'queued', %s)
            ON DUPLICATE KEY UPDATE run_id = run_id
            """,
            (cluster_name, obsids_csv, redshift, digest),
        )

        if cur.rowcount == 1:
            run_id = cur.lastrowid
            for obsid in obsids:
                cur.execute(
                    """
                    INSERT INTO pipeline_run_obsid (run_id, obsid)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE run_id = run_id
                    """,
                    (run_id, obsid),
                )
            created += 1
            print(
                f"Queued run_id={run_id} cluster='{cluster_name}' obsids={obsids_csv}"
            )
        else:
            skipped += 1

    db.commit()
    cur.close()
    db.close()
    print(f"Done. Created={created} skipped_existing={skipped}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Queue Lemur runs from a CSV or pickle manifest."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="Path to CSV file.")
    source.add_argument("--pickle", help="Path to pickle file.")
    parser.add_argument(
        "--delimiter", default=",", help="CSV delimiter (default: ',')."
    )
    parser.add_argument("--cluster-col", help="Cluster column name.")
    parser.add_argument("--obsid-col", help="ObsID column name.")
    parser.add_argument("--redshift-col", help="Optional redshift column name.")
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
