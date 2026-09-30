"""
Background Subtracted image from blank sky and other relevant functions

Functions:
    run_bkg_sub
    create_clean_img
    create_clean_image_merge
    exp_corr
"""

import os
import re

from ciao_contrib.runtool import *


def blanksky_chips(bkg_file):
    """ACIS chips that have a blank-sky background (its BKGSCALn keywords)."""
    from astropy.io import fits

    header = fits.getheader(bkg_file, 1)
    return sorted(
        int(m.group(1)) for key in header if (m := re.fullmatch(r"BKGSCAL(\d)", key))
    )


def run_bkg_sub(evt_file, image_file, obsid, filenames):
    """
    Create a blanksy event file and then subtract from image fits to create a
    background subtracted image for annuli creation
    PARAMETERS:
        evt_file - name of event file for creation of Blanksky
        image_file - Name of image from which the background will be subtracted
        obsid - current observation
        filenames - list of filenames
    """
    segments = filenames.get("evt2_repro_segments")
    if segments:
        # CIAO's blanksky refuses merged multi-OBI event files, so subtract the
        # background per segment and add the images; the segments share one
        # sky frame (same tangent point), so the images share one grid.
        parts = []
        for segment_file in segments:
            tag = os.path.basename(segment_file).split("_repro_evt2")[0][len("acisf") :]
            print(f"      Segment {tag}:")
            parts.append(_bkg_sub_one(segment_file, image_file, tag))
        output = obsid + "_blank_particle_bkgsub.img"
        dmimgcalc.punlearn()
        dmimgcalc.infile = ",".join(parts)
        dmimgcalc.outfile = output
        dmimgcalc.operation = "imgout=" + "+".join(
            f"img{i}" for i in range(1, len(parts) + 1)
        )
        dmimgcalc.clobber = True
        dmimgcalc()
    else:
        output = _bkg_sub_one(evt_file, image_file, obsid)
    # Add to file names
    filenames["evt_bkgsub_img"] = os.getcwd() + "/" + output
    return None


def _bkg_sub_one(evt_file, image_file, obsid):
    """Blank-sky background subtraction for one event file; returns the image."""
    print("      Creating blanksky event file...")
    # Create Blanksky File
    blanksky.punlearn()
    blanksky.evtfile = evt_file
    blanksky.outfile = obsid + "_blank.evt"
    blanksky.tmpdir = "./"
    blanksky.clobber = True
    blanksky()
    # Now create background subtracted image
    print("      Creating background-subtracted image")
    # CIAO 4.18 blanksky_image fails ("tuple.index(x): x not in tuple") when the
    # image has a chip with no blank-sky background ahead of chips that have
    # one. Rebin the same events (same full-range sky grid as image_file) using
    # only the chips the background covers, which is also the only area where
    # a background can be subtracted.
    chips = blanksky_chips(obsid + "_blank.evt")
    reference_image = image_file
    if chips:
        reference_image = obsid + "_bkgchips.img"
        dmcopy.punlearn()
        dmcopy.infile = f"{evt_file}[ccd_id={','.join(str(c) for c in chips)}]"
        dmcopy.outfile = reference_image
        dmcopy.opt = "image"
        dmcopy.clobber = True
        dmcopy()
    blanksky_image.punlearn()
    blanksky_image.bkgfile = obsid + "_blank.evt"
    blanksky_image.outroot = obsid + "_blank"
    blanksky_image.imgfile = reference_image
    blanksky_image.tmpdir = "./"
    blanksky_image.clobber = True
    blanksky_image()
    return obsid + "_blank_particle_bkgsub.img"


def create_clean_img(filenames):
    """
    Create a clean image by removing any pt sources from the extended emission
    PARAMETERS:
        filenames - dictionary of files
    """
    if (
        sum(1 for line in open("pt_srcs.reg")) < 3
    ):  # Dont actually clean b/c no pt sources
        dmcopy.punlearn()
        dmcopy.infile = filenames["evt2_repro"]
        dmcopy.outfile = filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
        dmcopy.clobber = True
        dmcopy()
    else:  # Here we need to exclude the pt srcs
        dmcopy.punlearn()
        dmcopy.infile = filenames["evt2_repro"] + "[exclude sky=region(pt_srcs.reg)]"
        dmcopy.outfile = filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
        dmcopy.clobber = True
        dmcopy()
    # Update uncontaminated filename
    filenames["evt2_repro_uncontam"] = (
        filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
    )
    # Create uncontaminated image
    dmcopy.punlearn()
    dmcopy.infile = filenames["evt2_repro_uncontam"]
    dmcopy.outfile = "evt_uncontam.img"
    dmcopy.opt = "image"
    dmcopy.clobber = True
    dmcopy()
    # update uncontaminated image
    filenames["evt_uncontam_img"] = os.getcwd() + "/" + "evt_uncontam.img"
    return None


def create_clean_img_merge(filenames):
    """
    Create clean merged image
    PARAMETERS:
        filenames - dictionary of files
    """
    dmcopy.punlearn()
    dmcopy.infile = filenames["evt2_repro"]
    dmcopy.outfile = filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
    dmcopy.clobber = True
    dmcopy()
    # Update uncontaminated filename
    filenames["evt2_repro_uncontam"] = (
        filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
    )
    # Create uncontaminated image
    dmcopy.punlearn()
    dmcopy.infile = filenames["evt2_repro_uncontam"]
    dmcopy.outfile = "evt_uncontam.img"
    dmcopy.opt = "image"
    dmcopy.clobber = True
    dmcopy()
    # update uncontaminated image
    filenames["evt_uncontam_img"] = "evt_uncontam.img"
    return None


def exp_corr(filenames):
    """
    Create exposure corrected image after background subtraction
    *** NOT CURRENTLY WORKING ***
    PARAMETERS:
        filenames - directory of files
    """
    fluximage.punlearn()
    fluximage.infile = filenames["evt_bkgsub_img"]
    fluximage.outroot = "flux/"
    fluximage.clobber = True
    fluximage()
    filenames["evt_bkgsub_img"] = os.getcwd() + "/flux/broad_flux.img"
    return None
