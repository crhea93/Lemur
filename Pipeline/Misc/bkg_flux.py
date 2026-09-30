"""Background-subtracted, exposure-corrected flux image for a merged object.

merge_obs / fluximage build broad_flux.img = broad_thresh.img / broad_thresh.expmap
from the cleaned event files. This module subtracts the blank-sky background:
for every ObsID (or ObsID segment) the blank-sky events written by blanksky
(<tag>_blank.evt in <obsid>/repro/) are reprojected onto the merged sky frame
(matching <cluster>/<tag>_reproj_evt.fits when merge_obs reprojected that
ObsID), filtered to the broad band, binned onto the grid of broad_thresh.img
and scaled per chip by BKGSCALn, as blanksky_image does. Then

    broad_flux.img = (broad_thresh.img - background) / broad_thresh.expmap

on every pixel with exposure (merge_obs's broad_thresh.expmap is already
zero below its exposure threshold); the image without background
subtraction is kept as broad_flux_nobkgsub.img and the background counts as
broad_bkg.img. The flux image gets BKGSUB = T.
"""

import glob
import os
import re
import shutil
import tempfile

import numpy as np
from astropy.io import fits
from ciao_contrib.runtool import blanksky, dmcopy, get_sky_limits, reproject_events

BAND_EV = (500, 7000)  # merge_obs / fluximage "broad" band
IMAGE = "broad_flux.img"
COUNTS = "broad_thresh.img"
EXPMAP = "broad_thresh.expmap"
RAW_COPY = "broad_flux_nobkgsub.img"
BKG_IMAGE = "broad_bkg.img"


def _chip_scales(blank_evt):
    header = fits.getheader(blank_evt, 1)
    return {
        int(m.group(1)): float(header[key])
        for key in header
        if (m := re.fullmatch(r"BKGSCAL(\d)", key))
    }


def _blank_files(home_dir, obsid):
    """(tag, blank-sky event file) for an ObsID, per segment when it has several."""
    repro = os.path.join(home_dir, obsid, "repro")
    found = []
    newest = {}
    for path in glob.glob(os.path.join(repro, f"{obsid}*_blank.evt*")):
        tag = os.path.basename(path).split("_blank.evt")[0]
        if tag == obsid or re.fullmatch(rf"{obsid}_\d{{3}}", tag):
            # A reprocessed ObsID can hold a new _blank.evt next to an older,
            # gzipped one; count each ObsID/segment once, using the newest.
            if tag not in newest or os.path.getmtime(path) > os.path.getmtime(
                newest[tag]
            ):
                newest[tag] = path
    found = sorted(newest.items())
    # Per-segment files supersede a whole-ObsID one left from an older run;
    # using both would count the background twice.
    if any(tag != obsid for tag, _ in found):
        found = [(tag, path) for tag, path in found if tag != obsid]
    return found


def _regenerate_blank(home_dir, obsid, workdir):
    """Recreate blank-sky events from the final repro evt2 (if they were pruned)."""
    repro = os.path.join(home_dir, obsid, "repro")
    events = sorted(glob.glob(os.path.join(repro, f"acisf{obsid}_repro_evt2.fits*")))
    if not events:
        return []
    out = os.path.join(workdir, f"{obsid}_blank.evt")
    blanksky.punlearn()
    blanksky(evtfile=events[0], outfile=out, tmpdir=workdir, clobber=True)
    return [(obsid, out)]


def _background_counts(blank_evt, match_evt, xygrid, workdir):
    """Scaled blank-sky counts image on the merged grid for one ObsID/segment."""
    scales = _chip_scales(blank_evt)
    source = blank_evt
    if match_evt:
        source = os.path.join(workdir, os.path.basename(blank_evt) + ".reproj")
        reproject_events.punlearn()
        # Blank-sky events have no TIME column, so random must not be -1.
        reproject_events(
            infile=blank_evt, outfile=source, match=match_evt, random=0, clobber=True
        )
    total = None
    for chip, scale in scales.items():
        image = os.path.join(workdir, f"bkg_chip{chip}.img")
        dmcopy.punlearn()
        dmcopy(
            infile=f"{source}[energy={BAND_EV[0]}:{BAND_EV[1]},ccd_id={chip}]"
            f"[bin {xygrid}]",
            outfile=image,
            option="image",
            clobber=True,
        )
        data = scale * fits.getdata(image).astype(np.float64)
        total = data if total is None else total + data
    return total


def make_bkgsub_flux(cluster_dir, home_dir, obsids, redo=False):
    """Replace cluster_dir/broad_flux.img by its background-subtracted version.

    Returns True on success. Objects already processed (BKGSUB = T) are left
    alone unless redo=True, which starts again from broad_flux_nobkgsub.img;
    on any failure the original image is kept.
    """
    image_path = os.path.join(cluster_dir, IMAGE)
    counts_path = os.path.join(cluster_dir, COUNTS)
    exp_path = os.path.join(cluster_dir, EXPMAP)
    if not all(os.path.exists(p) for p in (image_path, counts_path, exp_path)):
        print("    WARNING: background subtraction skipped (merge products missing)")
        return False
    if fits.getheader(image_path).get("BKGSUB") is True:
        raw_copy = os.path.join(cluster_dir, RAW_COPY)
        if not redo:
            return True
        if os.path.exists(raw_copy):
            shutil.copy2(raw_copy, image_path)
        elif os.path.exists(raw_copy + ".gz"):  # compressed after the run
            fits.open(raw_copy + ".gz").writeto(image_path, overwrite=True)
        else:
            print("    WARNING: cannot redo background subtraction (no raw copy)")
            return False

    get_sky_limits.punlearn()
    get_sky_limits(image=counts_path, verbose=0)
    xygrid = get_sky_limits.dmfilter

    with tempfile.TemporaryDirectory(dir=cluster_dir) as workdir:
        background = None
        used = []
        for obsid in obsids:
            obsid = str(obsid)
            blanks = _blank_files(home_dir, obsid) or _regenerate_blank(
                home_dir, obsid, workdir
            )
            if not blanks:
                print(f"    WARNING: no blank-sky background for ObsID {obsid}")
                continue
            for tag, blank_evt in blanks:
                match = os.path.join(cluster_dir, f"{tag}_reproj_evt.fits")
                bkg = _background_counts(
                    blank_evt, match if os.path.exists(match) else None, xygrid, workdir
                )
                if bkg is None:
                    continue
                background = bkg if background is None else background + bkg
                used.append(tag)
        if background is None:
            print("    WARNING: background subtraction skipped (no background images)")
            return False

    with fits.open(image_path) as flux_hdul, fits.open(counts_path) as counts_hdul:
        flux = flux_hdul[0].data.astype(np.float64)
        counts = counts_hdul[0].data.astype(np.float64)
        exposure = fits.getdata(exp_path).astype(np.float64)
        if not (flux.shape == counts.shape == exposure.shape == background.shape):
            print("    WARNING: background subtraction skipped (grid mismatch)")
            return False
        # Mask on exposure, not on flux != 0: at full resolution most exposed
        # pixels hold no photon, and they must still have the background
        # removed (becoming slightly negative), or the result is biased high.
        keep = exposure > 0
        subtracted = np.zeros_like(flux)
        subtracted[keep] = (counts[keep] - background[keep]) / exposure[keep]

        flux_hdul.writeto(os.path.join(cluster_dir, RAW_COPY), overwrite=True)
        header = flux_hdul[0].header.copy()
        header["BKGSUB"] = (True, "blank-sky background subtracted")
        header["BKGMETH"] = ("blanksky", "per-ObsID blank-sky events, BKGSCALn scaled")
        header.add_history(
            "LEMUR: (counts - blank-sky background) / expmap; background from "
            + ",".join(used)
        )
        fits.PrimaryHDU(subtracted.astype(np.float32), header).writeto(
            image_path, overwrite=True
        )
        bkg_header = counts_hdul[0].header.copy()
        bkg_header["BUNIT"] = "counts"
        fits.PrimaryHDU(background.astype(np.float32), bkg_header).writeto(
            os.path.join(cluster_dir, BKG_IMAGE), overwrite=True
        )
    print(f"    Background-subtracted {IMAGE} using {len(used)} blank-sky files")
    return True
