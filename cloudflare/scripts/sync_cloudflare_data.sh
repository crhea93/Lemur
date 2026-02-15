#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

D1_DB_NAME="lemur-db"
R2_BUCKET="lemur-fits"
SQL_DUMP_PATH="$ROOT_DIR/Pipeline/Lemur_DB.sql"
SQLITE_DB_PATH="$ROOT_DIR/api/data/lemur.db"
SCHEMA_FILE="$ROOT_DIR/cloudflare/sql/d1_schema.sql"
FITS_ROOT="$ROOT_DIR/api/data/fits"

SKIP_D1=0
SKIP_R2=0
SKIP_SCHEMA=0
DRY_RUN=0
KEEP_SQL_DUMP=0
CUSTOM_D1_DATA_SQL=""

usage() {
    cat <<'EOF'
Usage:
  cloudflare/scripts/sync_cloudflare_data.sh [options]

Options:
  --d1-db <name>            D1 database name (default: lemur-db)
  --r2-bucket <name>        R2 bucket name (default: lemur-fits)
  --sql-dump <path>         MySQL dump path (default: Pipeline/Lemur_DB.sql)
  --sqlite-db <path>        SQLite output path (default: api/data/lemur.db)
  --schema-file <path>      D1 schema SQL file (default: cloudflare/sql/d1_schema.sql)
  --fits-root <path>        Directory containing per-cluster FITS dirs (default: api/data/fits)
  --d1-data-sql <path>      Save generated SQLite dump SQL to this path
  --skip-d1                 Skip D1 sync
  --skip-r2                 Skip R2 FITS uploads
  --skip-schema             Skip schema apply (only import data into D1)
  --keep-sql-dump           Keep temp D1 data SQL file when --d1-data-sql is not set
  --dry-run                 Print commands without executing
  -h, --help                Show this help

Examples:
  cloudflare/scripts/sync_cloudflare_data.sh
  cloudflare/scripts/sync_cloudflare_data.sh --d1-db prod-db --r2-bucket prod-fits
  cloudflare/scripts/sync_cloudflare_data.sh --skip-r2
EOF
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing required command: $cmd" >&2
        exit 1
    fi
}

run_cmd() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] '
        printf '%q ' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --d1-db)
            D1_DB_NAME="$2"
            shift 2
            ;;
        --r2-bucket)
            R2_BUCKET="$2"
            shift 2
            ;;
        --sql-dump)
            SQL_DUMP_PATH="$2"
            shift 2
            ;;
        --sqlite-db)
            SQLITE_DB_PATH="$2"
            shift 2
            ;;
        --schema-file)
            SCHEMA_FILE="$2"
            shift 2
            ;;
        --fits-root)
            FITS_ROOT="$2"
            shift 2
            ;;
        --d1-data-sql)
            CUSTOM_D1_DATA_SQL="$2"
            shift 2
            ;;
        --skip-d1)
            SKIP_D1=1
            shift
            ;;
        --skip-r2)
            SKIP_R2=1
            shift
            ;;
        --skip-schema)
            SKIP_SCHEMA=1
            shift
            ;;
        --keep-sql-dump)
            KEEP_SQL_DUMP=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

require_cmd python3
require_cmd sqlite3
require_cmd wrangler

if [[ "$SKIP_R2" -eq 0 ]]; then
    require_cmd zip
fi

if [[ "$SKIP_D1" -eq 0 ]]; then
    if [[ ! -f "$SQL_DUMP_PATH" ]]; then
        echo "SQL dump not found: $SQL_DUMP_PATH" >&2
        exit 1
    fi
    if [[ "$SKIP_SCHEMA" -eq 0 && ! -f "$SCHEMA_FILE" ]]; then
        echo "Schema file not found: $SCHEMA_FILE" >&2
        exit 1
    fi
fi

if [[ "$SKIP_R2" -eq 0 && ! -d "$FITS_ROOT" ]]; then
    echo "FITS root not found: $FITS_ROOT" >&2
    exit 1
fi

D1_DATA_SQL=""
if [[ "$SKIP_D1" -eq 0 ]]; then
    if [[ -n "$CUSTOM_D1_DATA_SQL" ]]; then
        D1_DATA_SQL="$CUSTOM_D1_DATA_SQL"
        mkdir -p "$(dirname "$D1_DATA_SQL")"
    else
        D1_DATA_SQL="$(mktemp "${TMPDIR:-/tmp}/lemur_d1_data.XXXXXX.sql")"
    fi
fi

cleanup() {
    if [[ -n "$D1_DATA_SQL" && -z "$CUSTOM_D1_DATA_SQL" && "$KEEP_SQL_DUMP" -eq 0 ]]; then
        rm -f "$D1_DATA_SQL"
    fi
}
trap cleanup EXIT

if [[ "$SKIP_D1" -eq 0 ]]; then
    echo "==> Building SQLite from MySQL dump"
    run_cmd python3 "$ROOT_DIR/api/ingest_sql_dump.py" --sql "$SQL_DUMP_PATH" --db "$SQLITE_DB_PATH"

    echo "==> Exporting SQLite data to SQL for D1 import"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry-run] generate INSERT-only SQL for Clusters/Obsids/Region into '$D1_DATA_SQL'"
    else
        {
            echo "DELETE FROM Region;"
            echo "DELETE FROM Obsids;"
            echo "DELETE FROM Clusters;"
            sqlite3 "$SQLITE_DB_PATH" ".mode insert Clusters" "SELECT * FROM Clusters;"
            sqlite3 "$SQLITE_DB_PATH" ".mode insert Obsids" "SELECT * FROM Obsids;"
            sqlite3 "$SQLITE_DB_PATH" ".mode insert Region" "SELECT * FROM Region;"
        } > "$D1_DATA_SQL"
    fi

    if [[ "$SKIP_SCHEMA" -eq 0 ]]; then
        echo "==> Applying D1 schema to '$D1_DB_NAME'"
        run_cmd wrangler d1 execute "$D1_DB_NAME" --file "$SCHEMA_FILE" --remote
    else
        echo "==> Skipping D1 schema apply"
    fi

    echo "==> Importing data into D1 '$D1_DB_NAME'"
    run_cmd wrangler d1 execute "$D1_DB_NAME" --file "$D1_DATA_SQL" --remote

    if [[ -n "$CUSTOM_D1_DATA_SQL" || "$KEEP_SQL_DUMP" -eq 1 ]]; then
        echo "D1 data SQL saved at: $D1_DATA_SQL"
    fi
fi

if [[ "$SKIP_R2" -eq 0 ]]; then
    echo "==> Uploading FITS zips to R2 bucket '$R2_BUCKET'"

    tmp_zip_dir="$(mktemp -d "${TMPDIR:-/tmp}/lemur_fits_zip.XXXXXX")"
    trap 'rm -rf "$tmp_zip_dir"; cleanup' EXIT

    upload_count=0
    skip_count=0

    shopt -s nullglob
    for cluster_dir in "$FITS_ROOT"/*; do
        [[ -d "$cluster_dir" ]] || continue
        cluster_name="$(basename "$cluster_dir")"

        files=()
        while IFS= read -r -d '' f; do
            files+=("$f")
        done < <(find "$cluster_dir" -maxdepth 1 -type f \
            \( -iname "*.fits" -o -iname "*.fit" -o -iname "*.fts" -o -iname "*.gz" \) \
            -print0)

        if [[ "${#files[@]}" -eq 0 ]]; then
            echo " - Skipping $cluster_name (no FITS-like files found)"
            skip_count=$((skip_count + 1))
            continue
        fi

        zip_path="$tmp_zip_dir/${cluster_name}.zip"
        if [[ "$DRY_RUN" -eq 1 ]]; then
            echo "[dry-run] zip -j '$zip_path' <${#files[@]} files>"
        else
            rm -f "$zip_path"
            zip -j -q "$zip_path" "${files[@]}"
        fi

        target_key="fits/${cluster_name}.zip"
        run_cmd wrangler r2 object put "$R2_BUCKET/$target_key" --file "$zip_path" --remote
        echo " - Uploaded $cluster_name -> $R2_BUCKET/$target_key"
        upload_count=$((upload_count + 1))
    done

    echo "R2 upload summary: uploaded=$upload_count skipped=$skip_count"
fi

echo "Done."
