"""Losslessly shrink a finished pipeline run's working files.

Per processed ObsID folder: gzip large files in repro/ and Background/ (mostly
empty unbinned images, ~10x smaller), and drop the uncompressed copies that
Preliminary/unzip.py makes of archive files whose .fits.gz originals remain.
In the cluster folder: gzip large intermediate images, keeping the products
later steps read (broad_flux.img, broad_thresh.*, merged_evt.fits) as they are.
Nothing is lost: gunzip restores every file, and the pipeline regenerates the
unzipped copies when an ObsID is processed again.

    python scripts/compress_products.py --data-dir DIR --cluster NAME --obsids 1,2
"""

import argparse
import subprocess
import sys
from pathlib import Path

MIN_BYTES = 20_000_000
KEEP_IN_CLUSTER = {"broad_flux.img", "broad_thresh.img", "broad_thresh.expmap"}
KEEP_SUFFIXES = {".gz", ".png", ".reg", ".txt", ".lis", ".log", ".par"}


def gzip_large(folder, keep=()):
    saved = 0
    for path in sorted(folder.rglob("*")):
        if (
            not path.is_file()
            or path.is_symlink()
            or path.suffix in KEEP_SUFFIXES
            or path.name in keep
            or path.name == "merged_evt.fits"
        ):
            continue
        size = path.stat().st_size
        if size < MIN_BYTES:
            continue
        subprocess.run(["gzip", "-1", "-f", str(path)], check=True)
        saved += size - path.with_name(path.name + ".gz").stat().st_size
    return saved


def drop_unzipped_copies(obsid_dir):
    saved = 0
    for sub in ("primary", "secondary"):
        for gz in (obsid_dir / sub).glob("*.fits.gz"):
            copy = gz.with_suffix("")
            if copy.is_file():
                saved += copy.stat().st_size
                copy.unlink()
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--obsids", required=True, help="comma-separated")
    args = parser.parse_args(argv)

    root = Path(args.data_dir)
    saved = 0
    for obsid in [o.strip() for o in args.obsids.split(",") if o.strip()]:
        obsid_dir = root / obsid
        if not obsid_dir.is_dir():
            continue
        for sub in ("repro", "Background"):
            if (obsid_dir / sub).is_dir():
                saved += gzip_large(obsid_dir / sub)
        saved += drop_unzipped_copies(obsid_dir)
    cluster_dir = root / args.cluster
    if cluster_dir.is_dir():
        saved += gzip_large(cluster_dir, keep=KEEP_IN_CLUSTER)
    print(f"[compress] {args.cluster}: freed {saved / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
