"""Stage each object's downloadable images for the website's FITS zips.

For every object in the catalog database, puts into <fits-dir>/<name>/ (the
directory the R2 zips are built from, see `make publish-fits`):

    <name>_<band>_flux.fits.gz     background-subtracted, exposure-corrected image
    <name>_<band>_counts.fits.gz   counts image
    <name>_<band>_bkg.fits.gz      scaled blank-sky background (counts)

for band = broad (0.5-7 keV), soft (0.5-2 keV) and hard (2-7 keV). The
exposure map is (counts - bkg) / flux wherever there is exposure. Gzipped
sources are hard-linked (same drive, no extra space); others are gzipped.
A merged event file already in the directory is left as is.

    python scripts/stage_release_fits.py --data-dir DIR --fits-dir DIR [NAME ...]
"""

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline"))
from cluster_paths import resolve_cluster_file  # noqa: E402

# (band, product) -> image relative to the object's data folder (without .gz)
SOURCES = {
    ("broad", "flux"): "broad_flux.img",
    ("broad", "counts"): "broad_thresh.img",
    ("broad", "bkg"): "broad_bkg.img",
    ("soft", "flux"): "bands/soft_flux.img",
    ("soft", "counts"): "bands/soft_thresh.img",
    ("soft", "bkg"): "bands/soft_bkg.img",
    ("hard", "flux"): "bands/hard_flux.img",
    ("hard", "counts"): "bands/hard_thresh.img",
    ("hard", "bkg"): "bands/hard_bkg.img",
}


def stage(source, dest):
    """dest (.fits.gz) from source or source.gz; returns False if neither exists."""
    plain, packed = Path(source), Path(f"{source}.gz")
    if dest.exists():
        dest.unlink()
    if packed.exists() and (not plain.exists() or packed.stat().st_mtime >= plain.stat().st_mtime):
        try:
            os.link(packed, dest)
        except OSError:
            shutil.copy2(packed, dest)
        return True
    if plain.exists():
        with open(plain, "rb") as src, gzip.open(dest, "wb", 6) as out:
            shutil.copyfileobj(src, out)
        return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--fits-dir", required=True, help="Directory the R2 zips are built from")
    parser.add_argument("--db", default=str(ROOT / "api/data/lemur.db"))
    parser.add_argument("names", nargs="*", help="Only these objects")
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.db)
    names = args.names or [n for (n,) in con.execute("SELECT Name FROM Clusters ORDER BY Name")]
    con.close()
    staged = incomplete = missing = 0
    for name in names:
        broad = resolve_cluster_file(args.data_dir, name, "broad_flux.img")
        if broad is None:
            missing += 1
            print(f"{name}: no broad_flux.img", flush=True)
            continue
        out_dir = Path(args.fits_dir) / name
        out_dir.mkdir(parents=True, exist_ok=True)
        absent = [
            f"{band}_{product}"
            for (band, product), relative in SOURCES.items()
            if not stage(broad.parent / relative, out_dir / f"{name}_{band}_{product}.fits.gz")
        ]
        if absent:
            incomplete += 1
            print(f"{name}: missing {', '.join(absent)}", flush=True)
        else:
            staged += 1
    print(f"Staged {staged} objects; incomplete {incomplete}; without images {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
