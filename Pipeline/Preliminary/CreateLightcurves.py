"""
Python script to create lightcurves from the background
"""

import os

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from ciao_contrib.runtool import *
from lightcurves import *
from pycrates import *


def bkg_clean_srcs(bkg_ccd):
    """
    Remove any pt sources from the background CCD
    """
    vtpdetect.punlearn()
    vtpdetect.infile = bkg_ccd + ".fits"
    vtpdetect.outfile = bkg_ccd + "_src.fits"
    vtpdetect.regfile = bkg_ccd + "_src.reg"
    vtpdetect.clobber = True
    try:
        vtpdetect()
    except Exception as exc:
        # vtpdetect can fail on some deep/complex fields (stack recursion warnings).
        # Fall back to using the full background CCD rather than aborting the run.
        print(
            f"WARNING: vtpdetect failed on {bkg_ccd}. "
            f"Continuing without source-exclusion regions. Error: {exc}"
        )

    dmcopy.punlearn()
    reg_path = bkg_ccd + "_src.reg"
    has_regions = False
    try:
        if os.path.exists(reg_path) and os.path.getsize(reg_path) > 0:
            with open(reg_path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        has_regions = True
                        break
    except Exception:
        has_regions = False

    if has_regions:
        dmcopy.infile = bkg_ccd + ".fits[exclude sky=region(" + reg_path + ")]"
    else:
        dmcopy.infile = bkg_ccd + ".fits"
    dmcopy.outfile = bkg_ccd + "_bkg.fits"
    dmcopy.clobber = True
    dmcopy()

    return None


# If sigma clipping keeps less than this fraction of the event file's good time,
# the background light curve is unreliable (e.g. a faint background chip), so
# the event file's own GTI is used instead.
MIN_GTI_FRACTION = 0.1


def _gti_seconds(path):
    """Total good time in a GTI file (its GTI block; lc_sigma_clip puts it second)."""
    try:
        with fits.open(path) as hdul:
            data = hdul["GTI"].data
            if data is None or len(data) == 0:
                return 0.0
            return float(np.sum(data["STOP"] - data["START"]))
    except Exception:
        return 0.0


def _event_gti_seconds(event_file):
    """Good time of an event file: its longest GTI block (one per chip)."""
    try:
        with fits.open(event_file) as hdul:
            return max(
                (
                    float(np.sum(h.data["STOP"] - h.data["START"]))
                    for h in hdul
                    if h.name.startswith("GTI") and h.data is not None
                ),
                default=0.0,
            )
    except Exception:
        return 0.0


def bkg_lightcurve(bkg_ccd, obsid, create_plot=True):
    """
    Create and plot background lightcurve. Then create good-time-interval file
    """
    # Create Lightcurve
    dmextract.punlearn()
    dmextract.infile = bkg_ccd + "_bkg.fits[bin time=::200]"
    dmextract.outfile = bkg_ccd + "_bkg.lc"
    dmextract.opt = "ltc1"
    dmextract.clobber = True
    dmextract.verbose = 0
    dmextract()
    x = np.array([])
    y = np.array([])
    if create_plot:
        # Plot lightcurve using matplotlib
        lc_file = bkg_ccd + "_bkg.lc"
        try:
            with fits.open(lc_file, memmap=True) as hdul:
                data = hdul[1].data
                cols = data.columns.names
                x_key = "dt" if "dt" in cols else ("time" if "time" in cols else None)
                y_key = (
                    "count_rate"
                    if "count_rate" in cols
                    else ("rate" if "rate" in cols else None)
                )
                if x_key is None:
                    x = np.arange(len(data))
                else:
                    x = data[x_key]
                if y_key is None:
                    y = np.zeros(len(data))
                else:
                    y = data[y_key]
        except Exception:
            x = np.array([])
            y = np.array([])

        plt.figure(figsize=(6, 4))
        if len(x):
            plt.plot(x, y, color="#47f5ff", linewidth=1)
        plt.title("Light Curve")
        plt.xlabel("ΔT (s)")
        plt.ylabel("Rate (count s$^{-1}$)")
        plt.tight_layout()
        plt.savefig(bkg_ccd + "_bkg_lc.png", dpi=150)
        plt.close()

    # Clip image (no plot)
    gti_out = bkg_ccd + "_bkg_clean.gti"
    fallback_reason = None
    try:
        lc_sigma_clip(
            bkg_ccd + "_bkg.lc",
            gti_out,
            plot=False,
            sigma=3,
            pattern="none",
            verbose=0,
        )
        # A "successful" clip can still keep (almost) nothing, e.g. when the
        # background chip is too faint for a meaningful light curve; applying
        # that GTI would empty the observation.
        kept = _gti_seconds(gti_out)
        total = _event_gti_seconds(bkg_ccd + "_bkg.fits")
        if total > 0 and kept < MIN_GTI_FRACTION * total:
            fallback_reason = (
                f"sigma clipping kept {kept:.0f} s of {total:.0f} s "
                f"(< {MIN_GTI_FRACTION:.0%})"
            )
    except Exception as exc:
        # Some backgrounds are so faint they contain no positive count-rate rows.
        fallback_reason = f"lc_sigma_clip failed: {exc}"

    if fallback_reason:
        # Keep the pipeline moving with the GTI already in the event file.
        print(
            f"WARNING: {bkg_ccd}_bkg.lc: {fallback_reason}. "
            "Falling back to GTI from event file."
        )
        try:
            dmcopy.punlearn()
            dmcopy.infile = bkg_ccd + "_bkg.fits[GTI]"
            dmcopy.outfile = gti_out
            dmcopy.clobber = True
            dmcopy()
        except Exception as gti_exc:
            print(
                f"WARNING: unable to extract GTI block from {bkg_ccd}_bkg.fits. "
                "Flare filtering will be skipped for this OBSID. "
                f"Error: {gti_exc}"
            )

    if create_plot:
        plt.figure(figsize=(6, 4))
        if len(x):
            plt.plot(x, y, color="#ff4fd8", linewidth=1)
        plt.title("Light Curve")
        plt.xlabel("ΔT (s)")
        plt.ylabel("Rate (count s$^{-1}$)")
        plt.tight_layout()
        plt.savefig(obsid + "_Lightcurve.png", dpi=150)
        plt.close()
    return None
