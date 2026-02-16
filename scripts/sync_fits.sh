#!/usr/bin/env bash
set -euo pipefail

# Sync FITS files into the Lemur FITS directory from local disk or S3.
# Usage:
#   scripts/sync_fits.sh /path/to/source
#   scripts/sync_fits.sh s3://bucket/path
#   scripts/sync_fits.sh /path/to/source /custom/destination

SOURCE="${1:-}"
if [[ -z "${SOURCE}" ]]; then
  echo "Usage: $0 <source_dir|s3://bucket/path> [destination_dir]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEST="${2:-${LEMUR_FITS_DIR:-${LEMUR_DATA_DIR:-${REPO_ROOT}/api/data}/fits}}"
mkdir -p "${DEST}"

if [[ "${SOURCE}" == s3://* ]]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI not found. Install it to sync from S3." >&2
    exit 1
  fi
  aws s3 sync "${SOURCE}" "${DEST}" \
    --exclude "*" \
    --include "*.fits" \
    --include "*.fit" \
    --include "*.fts" \
    --include "*.fits.gz" \
    --include "*.fit.gz" \
    --include "*.fts.gz"
else
  if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync not found. Install rsync or use an S3 source with aws CLI." >&2
    exit 1
  fi
  rsync -av --prune-empty-dirs \
    --include "*/" \
    --include "*.fits" \
    --include "*.fit" \
    --include "*.fts" \
    --include "*.fits.gz" \
    --include "*.fit.gz" \
    --include "*.fts.gz" \
    --exclude "*" \
    "${SOURCE}/" "${DEST}/"
fi

echo "FITS sync complete: ${DEST}"
