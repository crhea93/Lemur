"""Background-subtract merged images of runs completed before 2026-09-30.

For each completed run in the rerun queue whose broad_flux.img lacks
BKGSUB = T, apply Misc.bkg_flux.make_bkgsub_flux (regenerating blank-sky
events from the final repro evt2 where they were pruned). Run inside the CIAO
env with its own PFILES directory if the queue worker is running:

    conda run -n ciao bash -c 'export PFILES="$(mktemp -d);$ASCDS_INSTALL/param";
        python scripts/backfill_bkgsub.py --data-dir DIR'
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from astropy.io import fits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline"))
from Misc.bkg_flux import make_bkgsub_flux  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--queue", default=str(ROOT / "api/data/rerun_queue.sqlite3"))
    parser.add_argument("clusters", nargs="*", help="Only these clusters")
    parser.add_argument("--redo", action="store_true", help="Redo already-done ones")
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.queue)
    runs = con.execute(
        "SELECT cluster_name, obsids_csv FROM pipeline_run WHERE status='completed'"
    ).fetchall()
    con.close()
    done = failed = skipped = 0
    for name, obsids in runs:
        if args.clusters and name not in args.clusters:
            continue
        image = Path(args.data_dir) / name / "broad_flux.img"
        if not image.exists():
            print(f"{name}: no broad_flux.img")
            failed += 1
            continue
        if fits.getheader(image).get("BKGSUB") is True and not args.redo:
            skipped += 1
            continue
        print(f"==> {name}", flush=True)
        try:
            ok = make_bkgsub_flux(
                str(image.parent), args.data_dir, obsids.split(","), redo=args.redo
            )
        except Exception as exc:
            print(f"    FAILED: {exc}")
            ok = False
        done += ok
        failed += not ok
    print(f"Background-subtracted {done}; failed {failed}; already done {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
