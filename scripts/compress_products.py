"""Shrink a finished pipeline run's working files.

Per processed ObsID folder:
  * gzip files over 1 MB in repro/, Background/, primary/ and secondary/
    (Preliminary/unzip.py decompresses archive .fits.gz files again if the
    ObsID is ever reprocessed), and drop uncompressed copies of archive files
    whose .fits.gz originals remain;
  * if the run completed, delete intermediates the pipeline regenerates from
    the archive files (Carter approved this on 2026-09-30 to fit the rerun on
    the drive): the evt1 copies in repro/ (*_evt1_deflared.fits,
    *_evt1_deflared_dstrk.fits, acis_new_evt1.fits) and the archive
    validation-report PDFs. The blank-sky background events (*_blank.evt) are
    kept (gzipped): background-subtracted images are built from them.
In the cluster folder: gzip large intermediate images, keeping the products
later steps read (broad_flux.img, broad_thresh.*, merged_evt.fits) as they are.

Superseded reductions: an object's previous reduction, moved aside to
<data-dir>/_previous_reductions/<cluster> before it was re-run, is deleted
once the new broad_flux.img exists with BKGSUB = T (written only by the new
pipeline), as approved by Carter on 2026-09-30 to fit the re-reduction.

A run counts as completed for an ObsID when its final repro evt2 exists and the
cluster's broad_flux.img was written after the intermediates. Failed runs keep
their intermediates (compressed) for debugging. --keep-intermediates disables
all deletion.

    python scripts/compress_products.py --data-dir DIR --cluster NAME --obsids 1,2
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MIN_BYTES = 1_000_000
KEEP_IN_CLUSTER = {"broad_flux.img", "broad_thresh.img", "broad_thresh.expmap"}
KEEP_SUFFIXES = {".gz", ".png", ".reg", ".txt", ".lis", ".log", ".par", ".jpg", ".pdf"}
INTERMEDIATES = {
    "repro": [
        "*_evt1_deflared.fits*",
        "*_evt1_deflared_dstrk.fits*",
        "acis_new_evt1.fits*",
    ],
    "secondary": ["*_vv*.pdf*"],
    ".": ["*_vv*.pdf*"],
}


def gzip_large(folder, keep=(), recursive=True):
    saved = 0
    paths = folder.rglob("*") if recursive else folder.glob("*")
    for path in sorted(paths):
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


def intermediates(obsid_dir):
    return [
        path
        for sub, patterns in INTERMEDIATES.items()
        for pattern in patterns
        for path in (obsid_dir / sub).glob(pattern)
        if path.is_file()
    ]


def run_completed(obsid_dir, obsid, cluster_image, files):
    """Final evt2 exists and the cluster image is newer than the intermediates."""
    repro = obsid_dir / "repro"
    has_final = any(repro.glob(f"acisf{obsid}*_repro_evt2.fits*"))
    if not has_final or not cluster_image.is_file():
        return False
    newest = max((p.stat().st_mtime for p in files), default=0.0)
    return cluster_image.stat().st_mtime >= newest


def new_image_complete(cluster_image):
    from astropy.io import fits

    try:
        return fits.getheader(cluster_image).get("BKGSUB") is True
    except Exception:
        return False


def remove_superseded(root, cluster, cluster_image):
    """Delete <root>/_previous_reductions/<cluster> (and <cluster>__<alias>)."""
    parent = root / "_previous_reductions"
    folders = [parent / cluster, *parent.glob(f"{cluster}__*")]
    folders = [f for f in folders if f.is_dir()]
    if not folders or not new_image_complete(cluster_image):
        return 0
    size = 0
    for folder in folders:
        size += sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
        shutil.rmtree(folder)
    return size


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--obsids", required=True, help="comma-separated")
    parser.add_argument("--keep-intermediates", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.data_dir)
    cluster_image = root / args.cluster / "broad_flux.img"
    saved = pruned = 0
    for obsid in [o.strip() for o in args.obsids.split(",") if o.strip()]:
        obsid_dir = root / obsid
        if not obsid_dir.is_dir():
            continue
        files = intermediates(obsid_dir)
        if not args.keep_intermediates and run_completed(
            obsid_dir, obsid, cluster_image, files
        ):
            for path in files:
                pruned += path.stat().st_size
                path.unlink()
        for sub in ("repro", "Background", "primary", "secondary"):
            if (obsid_dir / sub).is_dir():
                saved += gzip_large(obsid_dir / sub)
        saved += drop_unzipped_copies(obsid_dir)
    cluster_dir = root / args.cluster
    if cluster_dir.is_dir():
        saved += gzip_large(cluster_dir, keep=KEEP_IN_CLUSTER)
    if not args.keep_intermediates:
        pruned += remove_superseded(root, args.cluster, cluster_image)
    print(
        f"[compress] {args.cluster}: freed {(saved + pruned) / 1e9:.2f} GB "
        f"({pruned / 1e9:.2f} GB of regenerable intermediates deleted)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
