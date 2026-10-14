"""Soft and hard band images of an object, made at the end of a pipeline run.

Runs scripts/band_images.py (merge_obs per band and blank-sky background
subtraction, as for the broad band) and redraws the object's website previews
with scripts/band_previews.py. A failure here is reported but does not fail the
run, whose broad-band products are complete by then; scripts/run_band_pass.py
fills in any object still missing its band images. Set LEMUR_SKIP_BANDS=1 to
skip this step.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# name=lo:hi:effective energy (keV), as merge_obs takes them
BANDS = ("soft=0.5:2:1.25", "hard=2:7:3.8")


def make_band_images(inputs):
    """Soft/hard images and previews for inputs["name"]; True on success."""
    if os.environ.get("LEMUR_SKIP_BANDS") == "1":
        return False
    print("Making soft and hard band images...")
    images = [
        sys.executable,
        str(ROOT / "scripts" / "band_images.py"),
        "--data-dir",
        inputs["home_dir"],
        "--cluster",
        inputs["name"],
        "--obsids",
        ",".join(str(obsid) for obsid in inputs["dir_list"]),
    ]
    for band in BANDS:
        images += ["--band", band]
    previews = [
        sys.executable,
        str(ROOT / "scripts" / "band_previews.py"),
        "--data-dir",
        inputs["home_dir"],
        "--redo",
        inputs["name"],
    ]
    try:
        for command in (images, previews):
            subprocess.run(command, check=True, cwd=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"    WARNING: band images not made ({exc}); run scripts/run_band_pass.py later")
        return False
    return True
