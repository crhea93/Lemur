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
    vtpdetect()

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
    lc_sigma_clip(
        bkg_ccd + "_bkg.lc",
        bkg_ccd + "_bkg_clean.gti",
        plot=False,
        sigma=3,
        pattern="none",
        verbose=0,
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
