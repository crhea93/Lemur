"""Background-subtracted, exposure-corrected images of one object in extra bands.

Merges the object's cleaned event files with merge_obs at native ACIS
resolution in each band, then subtracts the blank-sky background as for the
catalogue's broad-band image (Misc.bkg_flux). Run inside the CIAO env:

    conda run -n ciao python scripts/band_images.py --data-dir DIR --cluster NGC253 \\
        --obsids 790,969 --band soft=0.5:2:1.25 --band hard=2:7:3.8

Writes <data-dir>/<cluster>/bands/<name>_flux.img (BKGSUB = T), plus the
counts, exposure map, background and unsubtracted images, for each band.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline"))
from Misc.bkg_flux import make_bkgsub_flux  # noqa: E402


def event_files(data_dir, obsid):
    """The cleaned event file(s) Merge.py would use for an ObsID."""
    repro = Path(data_dir) / obsid / "repro"
    segments = sorted(glob.glob(str(repro / f"acisf{obsid}_[0-9][0-9][0-9]_repro_evt2.fits*")))
    if segments:
        return segments
    for name in (f"acisf{obsid}_repro_evt2_uncontam.fits", f"acisf{obsid}_repro_evt2.fits"):
        found = sorted(glob.glob(str(repro / name)) + glob.glob(str(repro / (name + ".gz"))))
        if found:
            return found[:1]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--obsids", required=True, help="comma-separated")
    parser.add_argument(
        "--band",
        action="append",
        required=True,
        help="name=lo:hi:effective (keV), e.g. soft=0.5:2:1.25",
    )
    args = parser.parse_args(argv)

    obsids = [o.strip() for o in args.obsids.split(",") if o.strip()]
    files = [f for o in obsids for f in event_files(args.data_dir, o)]
    if not files:
        sys.exit("no event files found")
    out_dir = Path(args.data_dir) / args.cluster / "bands"
    out_dir.mkdir(parents=True, exist_ok=True)

    bands = {}
    for spec in args.band:
        name, rng = spec.split("=", 1)
        lo, hi, _eff = rng.split(":")
        bands[name] = (rng, f"{lo}-{hi}", (float(lo) * 1000, float(hi) * 1000))

    os.chdir(args.data_dir)  # make_bkgsub_flux finds <obsid>/repro from here
    subprocess.run(
        [
            "merge_obs",
            ",".join(files),
            f"{out_dir}/",
            f"bands={','.join(b[0] for b in bands.values())}",
            "binsize=1",
            "clobber=yes",
            "verbose=1",
        ],
        check=True,
    )
    for name, (_spec, prefix, band_ev) in bands.items():
        # merge_obs names custom bands "<lo>-<hi>"; give them the requested names.
        for suffix in ("_flux.img", "_thresh.img", "_thresh.expmap"):
            shutil.move(out_dir / f"{prefix}{suffix}", out_dir / f"{name}{suffix}")
        ok = make_bkgsub_flux(
            str(out_dir), args.data_dir, obsids, band=name, band_ev=band_ev
        )
        print(f"{name}: {'background-subtracted' if ok else 'FAILED'} -> {out_dir}/{name}_flux.img")
    return 0


if __name__ == "__main__":
    sys.exit(main())
