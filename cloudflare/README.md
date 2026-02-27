# Cloudflare Full-Stack Deployment (D1 + R2 + Worker Assets)

This folder scaffolds the Cloudflare-native deployment path for Lemur:
- Static site from `Web/` via Worker assets binding.
- API routes from a Worker (`cloudflare/src/worker.js`).
- Cluster metadata in D1 (`DB` binding).
- FITS ZIPs served directly from R2 (`FITS` binding).

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
- `bucket_name` under `[[r2_buckets]]` with the R2 bucket name.

## 3. Initialize D1 schema
```bash
wrangler d1 execute lemur-db --file cloudflare/sql/d1_schema.sql --remote
```

## 4. Import data into D1
Current production flow uses SQLite directly from `api/data/lemur.db`.

One practical path:
1. Export SQLite to SQL inserts:
   - `sqlite3 api/data/lemur.db .dump > cloudflare/sql/d1_data.sql`
2. Import into D1:
   - `wrangler d1 execute lemur-db --file cloudflare/sql/d1_data.sql --remote`

If your `.dump` includes SQLite internals, remove lines for `sqlite_sequence` before import.

## 5. Upload FITS archives to R2
Run the sync helper to package per-cluster FITS ZIPs and upload them to your R2 bucket.

## Automated sync for Steps 3, 4, and 5
Use the helper script to run D1 sync and R2 FITS uploads in one command:

```bash
./cloudflare/scripts/sync_cloudflare_data.sh
```

Useful flags:
- `--d1-db <name>` override D1 DB name
- `--r2-bucket <name>` override R2 bucket name for FITS ZIPs
- `--skip-schema` only import data (no schema apply)
- `--skip-d1` only run FITS uploads
- `--skip-fits` only run D1 sync
- `--dry-run` preview commands without executing

Examples:
```bash
./cloudflare/scripts/sync_cloudflare_data.sh --d1-db lemur-db
./cloudflare/scripts/sync_cloudflare_data.sh --skip-fits
./cloudflare/scripts/sync_cloudflare_data.sh --skip-d1
./cloudflare/scripts/sync_cloudflare_data.sh --r2-bucket lemur-fits
```

## 6. Deploy
```bash
wrangler deploy
```

After deploy, the same routes should work:
- `/`
- `/Table/index_table.html`
- `/stamps`
- `/cluster/<ClusterName>`
- `/api/clusters`
- `/api/stamps`
- `/api/clusters/<ClusterName>`
- `/api/fits/<ClusterName>/download`

## Notes
- Plot images are still served from `Web/Cluster_plots/*` static assets.
- FITS downloads are served from the R2 bucket bound as `FITS`.
- `worker.js` currently checks for `bkgsub_exp.png` in each cluster plot directory for the detail page.
