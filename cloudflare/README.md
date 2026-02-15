# Cloudflare Full-Stack Deployment (D1 + R2 + Worker Assets)

This folder scaffolds the Cloudflare-native deployment path for Lemur:
- Static site from `Web/` via Worker assets binding.
- API routes from a Worker (`cloudflare/src/worker.js`).
- Cluster metadata in D1 (`DB` binding).
- FITS download archives in R2 (`FITS_BUCKET` binding).

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
wrangler r2 bucket create lemur-fits
```

Then update `wrangler.toml`:
- `database_id` under `[[d1_databases]]` with the created D1 ID.
- `bucket_name` if you chose a different R2 name.

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

## 5. Upload FITS archives to R2
Worker expects one zip per cluster, with any of these keys:
- `fits/<ClusterName>.zip` (preferred)
- `<ClusterName>.zip`
- `<ClusterName>/<ClusterName>.zip`

Example:
```bash
wrangler r2 object put lemur-fits/fits/Abell133.zip --file ./path/to/Abell133.zip
```

## Automated sync for Steps 3 and 4
Use the helper script to run D1 schema+data sync and R2 FITS uploads in one command:

```bash
./cloudflare/scripts/sync_cloudflare_data.sh
```

Useful flags:
- `--d1-db <name>` override D1 DB name
- `--r2-bucket <name>` override R2 bucket name
- `--skip-schema` only import data (no schema apply)
- `--skip-d1` only run FITS uploads
- `--skip-r2` only run D1 sync
- `--dry-run` preview commands without executing

Examples:
```bash
./cloudflare/scripts/sync_cloudflare_data.sh --d1-db lemur-db --r2-bucket lemur-fits
./cloudflare/scripts/sync_cloudflare_data.sh --skip-r2
./cloudflare/scripts/sync_cloudflare_data.sh --skip-d1
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
- `worker.js` currently checks for `bkgsub_exp.png` in each cluster plot directory for the detail page.
