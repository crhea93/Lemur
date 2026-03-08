"""
Small script to merge objects

We are merging the background subtracted images in each obsid because we don't use the newly created evt file since
we only want the image for calculating the centroid, extent of emission, and annuli :)

"""

import os
import shutil
from pathlib import Path

from ciao_contrib.runtool import *


def merge_objects(Obsids, output_name, clean="yes"):
    """
    Merge background subtracted event files for photometric analysis
    PARAMETERS:
        Obsids - list of observation ids to merge
        output_name - name of output directory
        clean - clean up temporary files (default 'yes')
    """
    id_string = ""
    id_hyphen = ""
    found = False
    for obsid in Obsids:
        preferred = obsid + "/repro/acisf" + obsid + "_repro_evt2_uncontam.fits"
        fallback = obsid + "/repro/acisf" + obsid + "_repro_evt2.fits"
        if os.path.exists(preferred):
            id_string += preferred + ","
            found = True
        elif os.path.exists(fallback):
            id_string += fallback + ","
            found = True
        id_hyphen += obsid + "-"

    if not found:
        raise RuntimeError("merge_obs: no valid event files were found")
    os.system(
        "merge_obs '"
        + id_string
        + "' "
        + output_name
        + "/ clobber=yes verbose=0 cleanup="
        + clean
        + " bin=1 "
    )
    # Copy merged FITS to API download location with standardized name
    try:
        output_dir = Path(output_name)
        merged_evt = output_dir / "merged_evt.fits"
        if merged_evt.exists():
            repo_root = Path(__file__).resolve().parents[2]
            fits_dir = repo_root / "api" / "data" / "fits" / output_dir.name
            fits_dir.mkdir(parents=True, exist_ok=True)
            dest = fits_dir / f"{output_dir.name}.fits"
            shutil.copy2(merged_evt, dest)
    except Exception:
        pass
    return None
