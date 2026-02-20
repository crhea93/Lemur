# Cloudflare Full-Stack Deployment (D1 + Zenodo + Worker Assets)

This folder scaffolds the Cloudflare-native deployment path for Lemur:
- Static site from `Web/` via Worker assets binding.
- API routes from a Worker (`cloudflare/src/worker.js`).
- Cluster metadata in D1 (`DB` binding).
- FITS download links resolved from `Web/zenodo_fits_links.json` and redirected to Zenodo.

## 1. Prerequisites
- Node.js 18+.
- Cloudflare account.
- Wrangler CLI:
  - `npm i -D wrangler`
  - or `npm i -g wrangler`

## 2. Create Cloudflare resources
From repo root:

```bash
wrangler login
wrangler d1 create lemur-db
```

Then update `wrangler.toml`:
- `database_id` under `[[d1_databases]]` with the created D1 ID.

## 3. Initialize D1 schema
```bash
wrangler d1 execute lemur-db --file cloudflare/sql/d1_schema.sql --remote
```

## 4. Import data into D1
Current production flow generates SQLite in `api/data/lemur.db`.

One practical path:
1. Build/update local SQLite from pipeline output:
   - `python3 api/ingest_sql_dump.py --sql Pipeline/Lemur_DB.sql`
2. Export SQLite to SQL inserts:
   - `sqlite3 api/data/lemur.db .dump > cloudflare/sql/d1_data.sql`
3. Import into D1:
   - `wrangler d1 execute lemur-db --file cloudflare/sql/d1_data.sql --remote`

If your `.dump` includes SQLite internals, remove lines for `sqlite_sequence` before import.

## 5. Upload FITS archives to Zenodo
Run the sync helper to package per-cluster FITS zips, upload to Zenodo, and
generate `Web/zenodo_fits_links.json` used by the API/Worker download route.

Set your token first:
```bash
export ZENODO_TOKEN=your_token_here
```

## Automated sync for Steps 3, 4, and 5
Use the helper script to run D1 sync and Zenodo FITS uploads in one command:

```bash
./cloudflare/scripts/sync_cloudflare_data.sh
```

Useful flags:
- `--d1-db <name>` override D1 DB name
- `--zenodo-api-base <url>` set API base (e.g. `https://sandbox.zenodo.org/api`)
- `--zenodo-token <token>` pass token directly
- `--zenodo-links-file <path>` output links map
- `--skip-schema` only import data (no schema apply)
- `--skip-d1` only run FITS uploads
- `--skip-zenodo` only run D1 sync
- `--dry-run` preview commands without executing

Examples:
```bash
./cloudflare/scripts/sync_cloudflare_data.sh --d1-db lemur-db
./cloudflare/scripts/sync_cloudflare_data.sh --skip-zenodo
./cloudflare/scripts/sync_cloudflare_data.sh --skip-d1
./cloudflare/scripts/sync_cloudflare_data.sh --zenodo-api-base https://sandbox.zenodo.org/api --zenodo-token "$ZENODO_TOKEN"
```

## 6. Deploy
```bash
wrangler deploy
```

After deploy, the same routes should work:
- `/`
- `/Table/index_table.html`
- `/cluster/<ClusterName>`
- `/api/clusters`
- `/api/clusters/<ClusterName>`
- `/api/fits/<ClusterName>/download`

## Notes
- Plot images are still served from `Web/Cluster_plots/*` static assets.
- FITS links map is loaded from `Web/zenodo_fits_links.json`.
- `worker.js` currently checks for `bkgsub_exp.png` in each cluster plot directory for the detail page.
