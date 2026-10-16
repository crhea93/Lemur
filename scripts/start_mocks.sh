#!/usr/bin/env bash
# Start (or resume) the TNG mock run of configs/mocks.yaml, detached, as one
# systemd user scope capped at 40 GB. Each halo runs in its own process, so a
# halo killed for memory is only logged and retried on the next start.
# Run on the host: flatpak-spawn --host bash scripts/start_mocks.sh
set -euo pipefail
cd "$(dirname "$0")/.."
D=/run/media/crhea/ef10789c-0ada-41e4-8d3f-8f17dbcc0558
W=/run/media/crhea/kubuntu_2510/home/carterrhea/domain_gap_work
PY="$HOME/miniconda3/envs/tng-mocks/bin/python"
LOG="$D/_domain_gap/mocks_run.log"

running=$(ps -eo args | grep -F -- "-m domain_gap.mocks.run" | grep -v -E "grep|bash -c|flatpak-spawn" || true)
if [ -n "$running" ]; then
    echo "The mock run is already going; not starting another:"
    echo "$running"
    exit 1
fi
test -d "$D" || { echo "Data drive not mounted: $D"; exit 1; }
test -d "$W" || { echo "Work disk not mounted: $W"; exit 1; }

# Keep the scope's disk cache small so systemd-oomd does not kill it (see
# Lemur/api/data/cache_trimmer.sh); it trims every run-p*.scope.
TRIM="$HOME/Projects/Lemur/api/data/cache_trimmer.sh"
if [ -f "$TRIM" ] && ! pgrep -f "api/data/cache_trimmer.sh" > /dev/null; then
    systemd-run --user --unit="lemur-cache-trim-$(date +%s)" --collect \
        bash "$TRIM" > /dev/null 2>&1 || true
fi

export PYTHONPATH=. TMPDIR="$W" TQDM_DISABLE=1
mkdir -p "$D/_domain_gap"
echo "=== start $(date -Is)" >> "$LOG"
setsid nohup systemd-run --user --scope \
    -p MemoryMax=40G -p MemorySwapMax=2G -p OOMPolicy=continue \
    "$PY" -W ignore -m domain_gap.mocks.run --config configs/mocks.yaml \
    >> "$LOG" 2>&1 < /dev/null &
disown
echo "Mock run started; log: $LOG (per-halo logs in $D/_domain_gap/mocks/logs)"
