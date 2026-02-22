# Lemur
X-ray Galaxy Cluster Archive with a FastAPI backend and a modern web UI.

Live cluster website: https://lemur-archive.lemur-xray.workers.dev

[![CI](https://github.com/crhea93/Lemur/actions/workflows/ci.yml/badge.svg)](https://github.com/crhea93/Lemur/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-blue)](#development)

[![DOI](https://zenodo.org/badge/166745110.svg)](https://doi.org/10.5281/zenodo.18728228)



## Overview
This repository contains:
- A processing pipeline that generates a MySQL `.sql` dump of cluster data.
- A FastAPI backend that ingests the dump into SQLite and serves a JSON API.
- A modernized web UI that dynamically builds the cluster table and cluster detail pages.

## Structure
- `Pipeline/` - data processing code.
- `api/` - FastAPI app and SQL dump ingestion.
- `Web/` - static site assets and dynamic pages.
- `lemur.sql` - MySQL SQL dump used for API ingest.

## Quick Start (Web)
1. Create the SQLite database from the SQL dump:
```bash
lemur-ingest-sql --sql lemur.sql
# or script mode:
python3 api/ingest_sql_dump.py --sql lemur.sql
```

2. Run the API server:
```bash
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

3. Open in your browser:
- Cluster table: `http://localhost:8000/Table/index_table.html`
- Cluster detail page: `http://localhost:8000/cluster/Abell133`

Optional runtime paths (to keep data out of Git):
- `LEMUR_DATA_DIR` - base directory for runtime data (default: `api/data`)
- `LEMUR_DB_PATH` - full path to SQLite DB (default: `$LEMUR_DATA_DIR/lemur.db`)
- `LEMUR_FITS_DIR` - full path to FITS tree (default: `$LEMUR_DATA_DIR/fits`)

## Install (pip)
From repo root:

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[pipeline,test]"
```

Installed CLI commands:
- `lemur-pipeline`
- `lemur-ingest-sql`

## Pipeline
The pipeline is now orchestrated through `Pipeline/pipeline.py` and is split into
focused modules:
- `Pipeline/config.py` - input + env loading.
- `Pipeline/db.py` - DB connection + schema init.
- `Pipeline/db_service.py` - DB operations + API DB refresh.
- `Pipeline/preprocessing.py` - unzip/CCD/cleaning/merge prep.
- `Pipeline/surface_brightness.py` - SB profiling + coefficients.
- `Pipeline/web_export.py` - publish plots to the web tree.

### Run the pipeline
```bash
lemur-pipeline /path/to/input.i
# or module/script mode:
python -m Pipeline.pipeline /path/to/input.i
python Pipeline/pipeline.py /path/to/input.i
```

You can also run without creating an input file by passing cluster + obsids:
```bash
lemur-pipeline --cluster Abell133 --obsids 2203,9897
# or module/script mode:
python -m Pipeline.pipeline --cluster Abell133 --obsids 2203,9897
python Pipeline/pipeline.py --cluster Abell133 --obsids 2203,9897
```

This mode:
- Loads remaining parameters from `inputs/template.i` by default.
- Auto-sets `merge` from OBSID count.
- Resolves redshift from NED first, then CDS (Simbad) fallback.
- In merge mode, if `blanksky_image` fails for an OBSID, the run now logs a warning and continues with the cleaned image for that OBSID.

Optional flags:
```bash
lemur-pipeline --cluster Abell133 --obsids 2203 9897 --defaults /path/to/defaults.i
lemur-pipeline --cluster Abell133 --obsids 2203,9897 --redshift 0.0566
```

### Queue-Based Batch Runs (CSV -> Download -> Lemur)
This repo now includes an operations queue to process many clusters from a CSV manifest.

1. Create queue tables in MySQL:
```bash
mysql -u carterrhea -p carterrhea < Pipeline/sql/2026_02_16_pipeline_ops.sql
```

2. Enqueue runs from CSV:
```bash
python Pipeline/ops/enqueue_from_csv.py --csv /path/to/clusters.csv
```

Or from a pickle manifest:
```bash
python Pipeline/ops/enqueue_from_csv.py --pickle /path/to/clusters_grouped.pkl
```

If column names are non-standard, pass them explicitly:
```bash
python Pipeline/ops/enqueue_from_csv.py \
  --csv /path/to/clusters.csv \
  --cluster-col "Target Name" \
  --obsid-col "Obs ID" \
  --redshift-col redshift
```

3. Run the queue worker:
```bash
python Pipeline/ops/run_queue.py --defaults inputs/template.i
```

Useful flags:
- `--once` process one queued run then exit.
- `--retry-failed` include failed runs for retry.
- `--recover-interrupted` requeue runs left in `downloading/processing` after a crash/shutdown.
- `--skip-download` assume ObsIDs already exist in `home_dir`.
- `--download-cmd-template "download_chandra_obsid {obsid}"` customize fetch command.

Each run writes logs and metadata to:
- `Pipeline/ops/runs/<run_id>_<cluster>_<timestamp>/`

### Smoke test
Runs a real pipeline execution and verifies key outputs exist:
```bash
python Pipeline/smoke_test.py /path/to/input.i
```

The smoke test checks:
- `Additional.txt`
- `broad_flux.img`
- `broad_thresh.expmap`
- `bkg.reg`
- `merged_evt.fits` (if `merge = true`)

## API Endpoints
- `GET /api/health` - basic health check.
- `GET /api/clusters` - all clusters, including obsids.
- `GET /api/clusters/{name}` - cluster detail, obsids, region data, and plots.
- `GET /api/fits/{name}/download` - ZIP of FITS files for the cluster.

## FITS Downloads
FITS downloads are served from:
- `$LEMUR_FITS_DIR/<ClusterName>/<file>.fits` (or `.fit`, `.fts`, `.gz`)
- If `LEMUR_FITS_DIR` is unset, default is `api/data/fits/<ClusterName>/`

Sync helper:
```bash
scripts/sync_fits.sh /path/to/fits_source
scripts/sync_fits.sh s3://my-bucket/fits
```

If you use external hosted FITS URLs, configure your links source accordingly in
the API deployment environment.

## Dynamic Pages
- Table is rendered from `/api/clusters`.
- Cluster detail page is a single route: `/cluster/{name}`
  - Plots are loaded from `Web/Cluster_plots/{name}/` if present.

## Notes
- The SQL dump in `lemur.sql` is MySQL format; the ingest script converts it to SQLite.
- Client-side filtering remains in the table page.

## Development
If you update the pipeline output:
1. Regenerate `lemur.sql` (optional if `update_api = true`).
2. Re-run `lemur-ingest-sql`.
3. Restart the API if needed.

Code quality checks:
```bash
pip install -e ".[dev]"
ruff check tests api/app.py api/ingest_sql_dump.py Pipeline/config.py
black --check tests api/app.py api/ingest_sql_dump.py Pipeline/config.py
mypy api Pipeline/config.py Pipeline/pipeline.py tests
# with coverage output:
pytest --junitxml=pytest.xml --cov=api --cov=Pipeline.config --cov=Pipeline.pipeline --cov-report=term-missing --cov-report=xml
```
See `CONTRIBUTING.md` for the full contribution workflow.

## Cloudflare Deployment (Full Stack)
A starter Cloudflare-native setup has been added:
- `wrangler.toml`
- `cloudflare/src/worker.js`
- `cloudflare/sql/d1_schema.sql`
- `cloudflare/README.md`

This path runs:
- Static web assets from `Web/`
- API routes in a Worker
- Cluster metadata in D1
- FITS zip downloads from your configured FITS storage source

Follow `cloudflare/README.md` for provisioning and import steps.
For automated D1 + FITS metadata sync, use:
`./cloudflare/scripts/sync_cloudflare_data.sh`

### Makefile shortcuts
From repo root:

```bash
make deploy
make sync-all
make sync-d1
make sync-fits
make dry-run
```

## AI Disclosure
The frontend of this website and the FastAPI compilation/integration work were developed with assistance from Claude Code and ChatGPT Codex.

All scientific analysis code in this repository was written without the aid of AI.
