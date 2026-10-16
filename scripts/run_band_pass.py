"""Make soft/hard band images for every completed object in the rerun queue.

Resumable: objects whose bands/<band>_flux.img.gz exist are skipped. Runs
scripts/band_images.py per object (CIAO env, so start it inside `conda run -n
ciao`) and logs to api/data/band_pass.log; failures go to
api/data/band_pass_failures.txt.
"""

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline" / "ops"))
sys.path.insert(0, str(ROOT / "Pipeline"))
from Misc.band_products import BANDS  # noqa: E402
from run_queue import pipeline_safe_cluster_name  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--queue", default=str(ROOT / "api/data/rerun_queue.sqlite3"))
    parser.add_argument("clusters", nargs="*", help="Only these objects")
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.queue)
    runs = con.execute(
        "SELECT r.run_id, r.cluster_name, group_concat(o.obsid) FROM pipeline_run r "
        "JOIN pipeline_run_obsid o USING (run_id) WHERE r.status = 'completed' "
        "GROUP BY r.run_id ORDER BY r.run_id"
    ).fetchall()
    con.close()
    names = [b.split("=")[0] for b in BANDS]
    failures = open(ROOT / "api/data/band_pass_failures.txt", "a")
    done = failed = skipped = 0
    for run_id, cluster, obsids in runs:
        folder = pipeline_safe_cluster_name(cluster, run_id)
        if args.clusters and folder not in args.clusters and cluster not in args.clusters:
            continue
        bands_dir = Path(args.data_dir) / folder / "bands"
        if all((bands_dir / f"{n}_flux.img.gz").exists() for n in names):
            skipped += 1
            continue
        start = time.time()
        print(f"==> {folder} ({len(obsids.split(','))} ObsIDs)", flush=True)
        cmd = [sys.executable, str(ROOT / "scripts/band_images.py"),
               "--data-dir", args.data_dir, "--cluster", folder, "--obsids", obsids]
        for band in BANDS:
            cmd += ["--band", band]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            done += 1
            print(f"    ok in {time.time() - start:.0f} s", flush=True)
        else:
            failed += 1
            tail = (result.stdout + result.stderr).strip().splitlines()[-5:]
            print("    FAILED: " + " | ".join(tail), flush=True)
            failures.write(f"{folder}\t{' | '.join(tail)}\n")
            failures.flush()
    print(f"Band images made {done}; failed {failed}; already done {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
