from __future__ import annotations

import sqlite3

PIPELINE_RUN_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_run (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  cluster_name TEXT NOT NULL,
  obsids_csv TEXT NOT NULL,
  redshift_override REAL DEFAULT NULL,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','downloading','processing','completed','failed')),
  input_csv_row_hash TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  started_at TEXT DEFAULT NULL,
  finished_at TEXT DEFAULT NULL,
  error_text TEXT DEFAULT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(cluster_name, input_csv_row_hash)
);
"""

PIPELINE_RUN_OBSID_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_run_obsid (
  run_id INTEGER NOT NULL,
  obsid INTEGER NOT NULL,
  download_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (download_status IN ('pending','done','failed')),
  process_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (process_status IN ('pending','done','failed')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (run_id, obsid),
  FOREIGN KEY (run_id) REFERENCES pipeline_run(run_id) ON DELETE CASCADE
);
"""

PIPELINE_RUN_IDX_SQL = """
CREATE INDEX IF NOT EXISTS idx_pipeline_run_status_run_id
ON pipeline_run(status, run_id);
"""

PIPELINE_RUN_OBSID_IDX_SQL = """
CREATE INDEX IF NOT EXISTS idx_pipeline_run_obsid_run_id
ON pipeline_run_obsid(run_id);
"""

PIPELINE_RUN_UPDATED_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_pipeline_run_updated_at
AFTER UPDATE ON pipeline_run
FOR EACH ROW
BEGIN
  UPDATE pipeline_run
  SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE run_id = NEW.run_id;
END;
"""

PIPELINE_RUN_OBSID_UPDATED_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_pipeline_run_obsid_updated_at
AFTER UPDATE ON pipeline_run_obsid
FOR EACH ROW
BEGIN
  UPDATE pipeline_run_obsid
  SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE run_id = NEW.run_id AND obsid = NEW.obsid;
END;
"""


def ensure_sqlite_queue_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(PIPELINE_RUN_CREATE_SQL)
    conn.executescript(PIPELINE_RUN_OBSID_CREATE_SQL)
    conn.executescript(PIPELINE_RUN_IDX_SQL)
    conn.executescript(PIPELINE_RUN_OBSID_IDX_SQL)
    conn.executescript(PIPELINE_RUN_UPDATED_TRIGGER_SQL)
    conn.executescript(PIPELINE_RUN_OBSID_UPDATED_TRIGGER_SQL)
    conn.commit()
