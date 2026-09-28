"""Download the Chandra archive files needed to build broad_flux.img.

For each ObsID of every cluster that has no image yet, fetch the primary
evt2/asol/bpix/fov and secondary msk/dtf files into <data-dir>/<obsid>/primary
and .../secondary (the download_chandra_obsid layout, which merge_obs expects).
Only a few percent of a full archive download. Resumable: finished files are
skipped and partial downloads restart.

    python scripts/fetch_chandra_obsids.py --data-dir /path/to/Chandra
"""

import argparse
import re
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Pipeline"))
from cluster_paths import resolve_cluster_file  # noqa: E402

ARCHIVE = "https://cxc.cfa.harvard.edu/cdaftp/byobsid"
WANTED = {
    "primary": re.compile(r"(evt2|asol1|bpix1|fov1)\.fits\.gz$"),
    "secondary": re.compile(r"(msk1|dtf1)\.fits\.gz$"),
}


def fetch(url, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": "LemurArchive/1.0"})
    return urllib.request.urlopen(request, timeout=timeout)


def list_files(obsid, subdir):
    url = f"{ARCHIVE}/{obsid[-1]}/{obsid}/{subdir}/"
    try:
        with fetch(url) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception:
        return []
    names = set(re.findall(r'href="([^"/?]+)"', html))
    return sorted(n for n in names if WANTED[subdir].search(n))


def download(url, dest, retries=3):
    if dest.exists():
        return 0
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            with fetch(url) as resp, open(part, "wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            part.rename(dest)
            return dest.stat().st_size
        except Exception:
            time.sleep(2 * (attempt + 1))
    part.unlink(missing_ok=True)
    raise RuntimeError(f"failed to download {url}")


def fetch_obsid(obsid, data_dir):
    total = 0
    found_evt = False
    for subdir in WANTED:
        for name in list_files(obsid, subdir):
            found_evt |= "evt2" in name
            total += download(
                f"{ARCHIVE}/{obsid[-1]}/{obsid}/{subdir}/{name}",
                Path(data_dir) / obsid / subdir / name,
            )
    if not found_evt:
        raise RuntimeError("no evt2 in archive (proprietary or not ACIS/HRC?)")
    return total


def needed_obsids(db_path, search_dirs):
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT c.Name, GROUP_CONCAT(DISTINCT o.Obsid)
            FROM Clusters c JOIN Obsids o ON o.ClusterNumber = c.ID
            GROUP BY c.ID
            """
        ).fetchall()
    finally:
        con.close()
    obsids = set()
    for name, joined in rows:
        if resolve_cluster_file(search_dirs, name) is None:
            obsids.update(o.strip() for o in joined.split(",") if o.strip())
    return sorted(obsids, key=int)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True, help="Where ObsID dirs go")
    parser.add_argument("--sqlite-db", default="api/data/lemur.db")
    parser.add_argument("--search-dirs", help="':'-separated folders with images")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("obsids", nargs="*", help="Only these ObsIDs")
    args = parser.parse_args(argv)

    obsids = args.obsids or needed_obsids(
        args.sqlite_db, args.search_dirs or args.data_dir
    )
    print(f"Fetching {len(obsids)} ObsIDs with {args.workers} workers", flush=True)
    done = failed = 0
    fetched = 0
    start = time.time()
    failures = []
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(fetch_obsid, o, args.data_dir): o for o in obsids}
        for job in as_completed(jobs):
            obsid = jobs[job]
            try:
                fetched += job.result()
                done += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{obsid}\t{exc}\n")
            if (done + failed) % 50 == 0 or done + failed == len(obsids):
                rate = fetched / max(time.time() - start, 1) / 1e6
                print(
                    f"{done + failed}/{len(obsids)} done, {failed} failed, "
                    f"{fetched / 1e9:.1f} GB at {rate:.1f} MB/s",
                    flush=True,
                )
    if failures:
        log = Path(args.data_dir) / "fetch_failures.txt"
        log.write_text("".join(failures))
        print(f"Failures listed in {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
