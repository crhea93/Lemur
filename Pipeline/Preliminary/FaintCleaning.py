"""
This python script contains a full reprocessing suite to clean especially faint and extended X-ray observations

INPUTS:
chandra_dir -- path to chandra directory (i.e. '/home/usr/Documents/Data')
OBSID -- OBSID of interest (i.e. '#####')
source -- region file containing source -- only used for astrometric corrections (i.e. 'source.reg')
source_ra -- right ascension of source (i.e. '##:##:##.#')
source_dec -- declination of source (i.e. '##:##:##.#')
output_dir -- name of output directory (i.e. 'repro')
flare_gti -- gti file created from background flare cleaning (i.e. 'ccd2_bkg_clean.gti')

NOTES:
If running the Flares module assumes that we have already created a background light Curve
        and create a gti file from it in the primary directory

Observations taken in several segments (OBIs) are cleaned segment by segment,
each with its own flare GTI and matching evt1/flt1/mtl1/stat1/msk1/asol1/bias
files, and the per-segment event files are merged into the usual
acisf<OBSID>_repro_evt2.fits.
"""

import os

import matplotlib.pyplot as plt
from ciao_contrib.runtool import *
from Misc.filenames import get_filenames, get_segments
from Preliminary.BadPixel import BadPixel
from Preliminary.CreateLightcurves import segment_flare_gti
from Preliminary.Destreak import Destreak
from Preliminary.Flares import Flares
from Preliminary.Process import Process

# ----------------INPUTS-------------------#
output_dir = "repro"
# -----------------------------------------#


def FaintCleaning(chandra_dir, OBSID, ccd_bkg, source_ra, source_dec, ccds):
    """
    Reprocess data for a faint and diffuse object
    PARAMETERS:
            chandra_dir - path to chandra directory
            OBSID - OBSID of interest
            ccd_bkg - number of background ccd
            source_ra - right ascension of source
            source_dec - declination of source
            ccds - list of all ccd numbers
    """
    base_dir = chandra_dir + "/" + OBSID
    os.chdir(base_dir)
    filenames, biases = get_filenames()
    segments = get_segments()
    # print(filenames)
    if not os.path.exists(os.getcwd() + "/" + output_dir):
        os.makedirs(os.getcwd() + "/" + output_dir)
    if segments:
        return clean_segments(base_dir, OBSID, ccd_bkg, filenames, segments)
    os.chdir(base_dir + "/" + output_dir)
    # print("Appling Astrometric Corrections...")
    # Astrometric(OBSID,filenames,source_ra,source_dec)
    print("      Appling Background Flare Information...")
    os.chdir(base_dir)
    Flares(ccd_bkg + "_bkg_clean.gti", base_dir, output_dir, filenames)
    os.chdir(base_dir + "/" + output_dir)
    print("      Destreaking Event File...")
    Destreak(base_dir, output_dir, filenames)
    print("      Creating New Badpixel File...")
    BadPixel(base_dir, output_dir, OBSID, filenames, biases)
    print("      Apply GTI and Completing Reprocessing...")
    filenames = Process(filenames, OBSID)
    plt.close()
    return filenames


def clean_segments(base_dir, OBSID, ccd_bkg, filenames, segments):
    """Clean each segment (OBI) separately, then merge them into one evt2."""
    from astropy.io import fits

    print(f"      Observation has {len(segments)} segments; cleaning each...")
    segment_evt2 = []
    asol_files = []
    first_bpix = first_mask = None
    for seg in segments:
        tag = OBSID + "_" + seg["code"]
        print(f"      Segment {seg['code']}: flare GTI...")
        os.chdir(base_dir + "/Background")
        gti = segment_flare_gti(
            ccd_bkg,
            seg["tstart"],
            seg["tstop"],
            f"{ccd_bkg}_bkg_clean_obi{seg['code']}.gti",
        )
        seg_files = dict(filenames)
        for kind in ("evt1", "flt1", "msk1", "mtl1", "stat1"):
            seg_files[kind] = seg.get(kind, filenames.get(kind))
        seg_files["asol1"] = ",".join(seg["asol1"]) or filenames.get("asol1")
        seg_files["pbk0"] = seg.get("pbk0", filenames.get("pbk0"))
        seg_biases = sorted(seg["biases"]) or []
        for number, path in seg["biases"].items():
            seg_files[number + "_bias0"] = path

        os.chdir(base_dir)
        Flares(gti, base_dir, output_dir, seg_files)
        os.chdir(base_dir + "/" + output_dir)
        print(f"      Segment {seg['code']}: destreak, bad pixels, processing...")
        Destreak(base_dir, output_dir, seg_files)
        BadPixel(base_dir, output_dir, tag, seg_files, seg_biases)
        seg_files = Process(seg_files, tag)
        segment_evt2.append(seg_files["evt2_repro"])
        asol_files += seg["asol1"]
        first_bpix = first_bpix or seg_files["bpix_repro"]
        first_mask = first_mask or seg_files.get("msk1")

    combined = "acisf" + OBSID + "_repro_evt2.fits"
    print("      Merging segments into " + combined)
    dmmerge.punlearn()
    dmmerge.infile = ",".join(segment_evt2)
    dmmerge.outfile = combined
    dmmerge.clobber = True
    dmmerge()
    # Point CIAO's ancillary-file lookup at every segment's aspect solution so
    # exposure maps cover all segments.
    with fits.open(combined, mode="update") as hdul:
        header = hdul["EVENTS"].header
        header["ASOLFILE"] = ",".join(os.path.basename(p) for p in asol_files)
        header["BPIXFILE"] = os.path.basename(first_bpix)
        if first_mask:
            header["MASKFILE"] = os.path.basename(first_mask)
    filenames["evt2_repro"] = combined
    filenames["bpix_repro"] = first_bpix
    # CIAO imaging tools (fluximage/merge_obs) require multi-OBI data as one
    # event file per segment, so keep those for the flux image.
    filenames["evt2_repro_segments"] = [
        base_dir + "/" + output_dir + "/" + name for name in segment_evt2
    ]
    plt.close()
    return filenames
