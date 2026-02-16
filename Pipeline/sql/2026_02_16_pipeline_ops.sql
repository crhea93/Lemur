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
);

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
);
