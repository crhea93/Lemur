"""Build broad_flux.img for clusters whose ObsIDs are on disk but never merged.

Mirrors Pipeline/Preliminary/Merge.py: merge_obs over each ObsID's reprocessed
event file (preferring the _uncontam version), falling back to the archive
primary evt2, with binsize=1. Outputs (broad_flux.img, broad_thresh.expmap,
merged_evt.fits, ...) go to <data-dir>/<cluster>/.

Run inside a CIAO environment, e.g.:
    conda run -n ciao python scripts/build_flux_images.py --data-dir /path/to/Chandra
"""

import argparse
import glob
import os
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Pipeline"))
from cluster_paths import resolve_cluster_file  # noqa: E402


def event_file(data_dir, obsid):
    base = Path(data_dir) / obsid
    for pattern in (
        f"repro/acisf*{obsid}_repro_evt2_uncontam.fits",
        f"repro/acisf*{obsid}_repro_evt2.fits",
        "primary/*evt2.fits*",
    ):
        matches = sorted(glob.glob(str(base / pattern)))
        if matches:
            return matches[0]
    return None


def cluster_obsids(db_path):
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT c.Name, GROUP_CONCAT(o.Obsid)
            FROM Clusters c JOIN Obsids o ON o.ClusterNumber = c.ID
            GROUP BY c.ID ORDER BY c.Name
            """
        ).fetchall()
    finally:
        con.close()
    return {name: sorted(set(obsids.split(","))) for name, obsids in rows}


def build(name, event_files, out_dir, dry_run=False):
    out_dir.mkdir(exist_ok=True)
    stack = out_dir / "merge_obs_inputs.lis"
    stack.write_text("".join(f"{path}\n" for path in event_files))
    cmd = [
        "merge_obs",
        f"@{stack}",
        f"{out_dir}/",
        "bands=broad",
        "binsize=1",
        "clobber=yes",
        "cleanup=yes",
        "verbose=0",
    ]
    if dry_run:
        print(f"==> {name}: {len(event_files)} ObsID(s)\n    " + " ".join(cmd))
        return True
    # Parallel CIAO runs must not share parameter files: give each its own
    # user PFILES directory in front of the system one.
    with tempfile.TemporaryDirectory() as pfiles:
        system_pfiles = os.environ.get("PFILES", "").split(";")[-1]
        env = {**os.environ, "PFILES": f"{pfiles};{system_pfiles}"}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (out_dir / "merge_obs.log").write_text(result.stdout + result.stderr)
    ok = result.returncode == 0 and (out_dir / "broad_flux.img").exists()
    status = "ok" if ok else f"FAILED ({result.returncode}), see merge_obs.log"
    print(f"==> {name}: {len(event_files)} ObsID(s) {status}", flush=True)
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True, help="Folder with ObsID dirs")
    parser.add_argument("--sqlite-db", default="api/data/lemur.db")
    parser.add_argument(
        "--search-dirs",
        help="Folders (':'-separated) checked for existing images; default data-dir",
    )
    parser.add_argument("clusters", nargs="*", help="Only these clusters")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=6, help="Parallel merges")
    args = parser.parse_args(argv)

    search = args.search_dirs or args.data_dir
    jobs, skipped = [], []
    for name, obsids in cluster_obsids(args.sqlite_db).items():
        if args.clusters and name not in args.clusters:
            continue
        if not args.clusters and resolve_cluster_file(search, name) is not None:
            continue
        events = [e for e in (event_file(args.data_dir, o) for o in obsids) if e]
        if not events:
            skipped.append(name)
            continue
        if len(events) < len(obsids):
            print(f"    {name}: {len(obsids) - len(events)} ObsID(s) not on disk")
        jobs.append((name, events, Path(args.data_dir) / name))

    print(f"Building {len(jobs)} clusters with {args.workers} workers", flush=True)
    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        results = list(
            pool.map(lambda job: (job[0], build(*job, dry_run=args.dry_run)), jobs)
        )
    built = [name for name, ok in results if ok]
    failed = [name for name, ok in results if not ok]

    print(f"Built {len(built)}; failed {len(failed)}: {failed}")
    print(f"No event files on disk for {len(skipped)} clusters (not built).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
