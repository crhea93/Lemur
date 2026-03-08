# Lemur
X-ray Galaxy Cluster Archive with a FastAPI backend and a modern web UI.

Live cluster website: https://lemur-archive.lemur-xray.workers.dev

[![CI](https://github.com/crhea93/Lemur/actions/workflows/ci.yml/badge.svg)](https://github.com/crhea93/Lemur/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-blue)](#development)
[![DOI](https://zenodo.org/badge/166745110.svg)](https://doi.org/10.5281/zenodo.18728228)

## Quick Start
1. Create the SQLite database from the SQL dump:
```bash
lemur-ingest-sql --sql lemur.sql
# or:
python3 api/ingest_sql_dump.py --sql lemur.sql
```

2. Run the API + static site:
```bash
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

3. Open:
- `http://localhost:8000/Table/index_table.html`
- `http://localhost:8000/cluster/Abell133`

Optional runtime paths:
- `LEMUR_DATA_DIR` (default: `api/data`)
- `LEMUR_DB_PATH` (default: `$LEMUR_DATA_DIR/lemur.db`)
- `LEMUR_FITS_DIR` (default: `$LEMUR_DATA_DIR/fits`)

## Install
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
Pipeline code lives in `Pipeline/` and is orchestrated by `Pipeline/pipeline.py`.

Run with an input file:
```bash
lemur-pipeline /path/to/input.i
```

Run by cluster + ObsIDs:
```bash
lemur-pipeline --cluster Abell133 --obsids 2203,9897
```

## API
Primary endpoints:
- `GET /api/health`
- `GET /api/clusters`
- `GET /api/clusters/{name}`
- `GET /api/fits/{name}/download`
- `GET /api/stamps`

FITS downloads are served from `$LEMUR_FITS_DIR` (or `api/data/fits` by default).

Sync helper:
```bash
scripts/sync_fits.sh /path/to/fits_source
scripts/sync_fits.sh s3://my-bucket/fits
```

## Cloudflare Deployment
Cloudflare Worker + D1 setup is documented in:
- `cloudflare/README.md`

Useful shortcuts:
```bash
make deploy
make sync-all
make sync-d1
make sync-fits
make dry-run
```

## Development
For contribution workflow, linting, typing, and test commands, see:
- `CONTRIBUTING.md`
