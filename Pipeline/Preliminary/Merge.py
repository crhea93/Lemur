"""
Small script to merge objects

We are merging the background subtracted images in each obsid because we don't use the newly created evt file since
we only want the image for calculating the centroid, extent of emission, and annuli :)

"""

import glob
import os
import shlex
import shutil
import sys
from pathlib import Path

from ciao_contrib.runtool import *


def is_grating(event_file):
    """True for HETG/LETG observations, which LEMUR excludes (ACIS imaging only)."""
    from astropy.io import fits

    try:
        grating = fits.getheader(event_file, "EVENTS").get("GRATING", "NONE")
    except Exception:
        return False
    return str(grating).strip().upper() not in ("NONE", "")


# merge_obs holds several float32 images of the full mosaic grid in memory, in
# two places (CIAO's own estimates, fluximage.Project_Memory_Use):
#   - one process per ObsID builds its exposure map: ~(6 + chips) images each
#     (13 grid-sized copies measured for dmimgcalc on Centaurus);
#   - the final co-add of N per-ObsID images: ~(12 + 2 N) images.
# Wide mosaics at binsize=1 then exceed the worker's 40 GB memory cap, so limit
# the parallel processes and the images added at once to a memory budget.
MERGE_MEMORY_BUDGET = 16e9  # leaves room for page cache under the 40 GB cap
BYTES_PER_GRID_PIXEL = 13 * 4
ACIS_FIELD_ARCMIN = 30  # margin around the pointings for the chips' extent
GRID_SAFETY = 1.5  # real grids are up to ~1.5x the estimate (roll angle, chip layout)
COADD_MAX_IMAGES = 100  # merge_obs adds at most this many images in one call


def _grid_pixels(event_files):
    """Estimated number of pixels in the merged image, or None if unknown."""
    from astropy.coordinates import SkyCoord
    from astropy.io import fits

    ra, dec = [], []
    for event_file in event_files:
        try:
            header = fits.getheader(event_file, "EVENTS")
            ra.append(float(header["RA_PNT"]))
            dec.append(float(header["DEC_PNT"]))
        except Exception:
            continue
    if not ra:
        return None
    points = SkyCoord(ra, dec, unit="deg")
    centre = SkyCoord(ra[0], dec[0], unit="deg")
    offsets = centre.spherical_offsets_to(points)
    side = [
        (max(o.arcmin) - min(o.arcmin) + ACIS_FIELD_ARCMIN) * 60 / 0.492
        for o in offsets
    ]
    return GRID_SAFETY * side[0] * side[1]


def merge_nproc(event_files):
    """Number of parallel merge_obs processes that fits MERGE_MEMORY_BUDGET."""
    pixels = _grid_pixels(event_files)
    if pixels is None:
        return 1
    grid_bytes = pixels * BYTES_PER_GRID_PIXEL
    return max(1, min(os.cpu_count() or 1, int(MERGE_MEMORY_BUDGET // grid_bytes)))


def merge_nchunk(event_files):
    """Images merge_obs may co-add at once, or None when all of them fit."""
    pixels = _grid_pixels(event_files)
    if pixels is None:
        return None
    image_bytes = 4 * pixels
    at_once = min(len(event_files), COADD_MAX_IMAGES)
    if (12 + 2 * at_once) * image_bytes <= MERGE_MEMORY_BUDGET:
        return None
    return max(2, int((MERGE_MEMORY_BUDGET / image_bytes - 12) // 2))


def merge_obs_tool(event_files):
    """Command (argument list) for merge_obs, co-adding in chunks when needed."""
    nchunk = merge_nchunk(event_files)
    if nchunk is None:
        return ["merge_obs"]
    wrapper = Path(__file__).with_name("merge_obs_chunked.py")
    return [sys.executable, str(wrapper), str(nchunk)]


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
        # Multi-segment (multi-OBI) ObsIDs: CIAO needs one event file per
        # segment; the merge path's "_uncontam" file is a plain copy anyway.
        segments = sorted(
            glob.glob(f"{obsid}/repro/acisf{obsid}_[0-9][0-9][0-9]_repro_evt2.fits")
        )
        candidates = segments or glob.glob(f"{obsid}/repro/acisf{obsid}_repro_evt2*.fits")
        if candidates and is_grating(candidates[0]):
            print(f"    WARNING: skipping grating ObsID {obsid} (ACIS imaging only)")
            continue
        if segments:
            id_string += ",".join(segments) + ","
            found = True
            id_hyphen += obsid + "-"
            continue
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
    event_files = [f for f in id_string.split(",") if f]
    nproc = merge_nproc(event_files)
    tool = merge_obs_tool(event_files)
    print(
        f"    merge_obs with nproc={nproc}"
        + (f", co-adding {tool[-1]} images at a time" if len(tool) > 1 else "")
    )
    # Pass the inputs as a stack file: CIAO truncates a parameter string at
    # ~2000 characters, which silently dropped ObsIDs beyond about the 41st
    # (Abell2146, M31, SgrA). "@-": the entries are relative to the working
    # directory, not to the stack file's folder.
    os.makedirs(output_name, exist_ok=True)
    stack = os.path.join(output_name, "merge_inputs.lis")
    with open(stack, "w") as handle:
        handle.write("\n".join(event_files) + "\n")
    os.system(
        " ".join(shlex.quote(part) for part in tool)
        + " '@-"
        + stack
        + "' "
        + output_name
        + "/ clobber=yes verbose=0 cleanup="
        + clean
        + " bin=1 nproc="
        + str(nproc)
    )
    # Copy merged FITS to API download location with standardized name
    try:
        output_dir = Path(output_name)
        merged_evt = output_dir / "merged_evt.fits"
        if merged_evt.exists():
            repo_root = Path(__file__).resolve().parents[2]
            fits_root = Path(
                os.getenv("LEMUR_FITS_DIR", str(repo_root / "api" / "data" / "fits"))
            ).expanduser()
            fits_dir = fits_root / output_dir.name
            fits_dir.mkdir(parents=True, exist_ok=True)
            dest = fits_dir / f"{output_dir.name}.fits"
            shutil.copy2(merged_evt, dest)
    except Exception:
        pass
    return None
