CSV Targets to Queue Runs: How the Current Database Was Built
==============================================================

This page documents the operational workflow you described:

1. Build a CSV of targets/ObsIDs.
2. Ingest that CSV into queue tables.
3. Run the queue worker so each queued target executes the Lemur pipeline.

The commands and behavior here map directly to:

- ``Pipeline/ops/enqueue_from_csv.py``
- ``Pipeline/ops/run_queue.py``

Overview
--------

The queue system separates *planning* from *execution*:

- Planning step inserts one row per target into ``pipeline_run`` and one row per
  target/obsid pair into ``pipeline_run_obsid``.
- Execution step claims queued rows, downloads ObsIDs (unless skipped), runs
  ``Pipeline/pipeline.py``, and marks each run completed or failed.

Step 0: Queue DB and tables
---------------------------

Queue orchestration is now SQLite-native. Queue tables are created automatically
when enqueue/worker scripts run.

Default queue DB path:

- ``Pipeline/ops/pipeline_queue.sqlite3``
- or set ``LEMUR_QUEUE_DB`` to override.

Main tables:

- ``pipeline_run``: one queued run per cluster target.
- ``pipeline_run_obsid``: child rows with per-obsid download/process status.

Optional one-time historical migration
--------------------------------------

If you already have historical queue data in MySQL, migrate it once with:

.. code-block:: bash

   pip install -e ".[queue_migration]"

.. code-block:: bash

   python Pipeline/ops/migrate_queue_mysql_to_sqlite.py --sqlite-db Pipeline/ops/pipeline_queue.sqlite3

Step 1: Prepare the target CSV
------------------------------

Minimum required columns:

- cluster name column (examples accepted: ``cluster``, ``cluster_name``, ``name``,
  ``target name``)
- obsid column (examples accepted: ``obsid``, ``obs id``, ``obsids``, ``dir_list``)

Optional:

- redshift column (examples accepted: ``redshift`` or ``z``)

ObsID parsing accepts comma-separated and mixed text; digits are extracted and
deduplicated.

Example CSV:

.. code-block:: text

   cluster_name,obsids,redshift
   Abell133,"2203,9897",0.0566
   A2029,"4977 6101",0.0767

Step 2: Ingest CSV rows into queue tables
-----------------------------------------

Run:

.. code-block:: bash

   python Pipeline/ops/enqueue_from_csv.py \
     --csv /path/to/targets.csv \
     --sqlite-db Pipeline/ops/pipeline_queue.sqlite3

If headers are non-standard, pass explicit mappings:

.. code-block:: bash

   python Pipeline/ops/enqueue_from_csv.py \
     --csv /path/to/targets.csv \
     --cluster-col "Target Name" \
     --obsid-col "Obs ID" \
     --redshift-col redshift

What enqueue does:

1. Groups rows by cluster name.
2. Unions/deduplicates ObsIDs per cluster.
3. Inserts one ``pipeline_run`` row with:
   - ``status='queued'``
   - ``obsids_csv`` as normalized comma list
   - ``redshift_override`` when available
4. Inserts ``pipeline_run_obsid`` rows (one per ObsID) with
   ``download_status='pending'`` and ``process_status='pending'``.

Idempotency note:

- ``pipeline_run`` has a unique key on ``(cluster_name, input_csv_row_hash)``,
  so repeated ingestion of unchanged target rows is safely deduplicated.

Step 3: Run the queue worker
----------------------------

Start the worker:

.. code-block:: bash

   python Pipeline/ops/run_queue.py \
     --defaults inputs/template.i \
     --sqlite-db Pipeline/ops/pipeline_queue.sqlite3

Worker lifecycle per run:

1. Atomically claims the next row from ``pipeline_run`` (status transitions to
   ``downloading`` and ``attempts`` increments).
2. Downloads ObsIDs using the configured download command template
   (unless ``--skip-download`` is used).
3. Updates run status to ``processing``.
4. Executes ``Pipeline/pipeline.py --cluster ... --obsids ... --defaults ...``.
5. Marks all obsids ``process_status='done'`` and run status ``completed``.
6. On error, marks run ``failed`` and records error text.

Worker outputs per run:

- ``Pipeline/ops/runs/<run_id>_<cluster>_<timestamp>/run.json``
- ``Pipeline/ops/runs/<run_id>_<cluster>_<timestamp>/runner.log``

Useful worker flags
-------------------

- ``--once``: process one run and exit.
- ``--retry-failed``: include failed runs (up to max attempts).
- ``--recover-interrupted``: requeue runs left in ``downloading`` or ``processing``.
- ``--skip-download``: assume ObsIDs are already present on disk.
- ``--download-cmd-template "download_chandra_obsid {obsid}"``: override downloader.

Step 4: How this populates the scientific DB
--------------------------------------------

Each queue run executes the standard Lemur pipeline workflow for that target.
During those runs, the pipeline writes/updates scientific tables (cluster rows,
obsid links, fit regions, derived quantities) in the configured runtime DB.

In practical terms: queue orchestration controls *which* targets run and *when*;
the pipeline code controls *how* each target contributes rows to the database.

Step 5: Operational checks during production runs
-------------------------------------------------

Recommended checks while the worker is active:

1. Queue depth and status mix in ``pipeline_run``.
2. Per-obsid status in ``pipeline_run_obsid``.
3. ``runner.log`` tail for the current run directory.
4. Failed-run export file (if configured), then rerun with ``--retry-failed``
   after fixing root causes.

End-to-end summary
------------------

The production path is:

``target CSV -> enqueue_from_csv.py -> pipeline_run tables -> run_queue.py -> pipeline.py per target -> updated Lemur database``.

That is the exact procedure used to drive bulk target processing for the current
cluster/galaxy catalog build.
