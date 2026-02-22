"""
Create window with all ccds
"""

import os
from shutil import copyfile

import numpy as np
from astropy.io import fits
from ciao_contrib.runtool import *


# -----------------------------CLASSES----------------------------------#
class AGN:
    """
    Class to handle potential AGN. We must contain the central point of the AGN
    and its radius. We also will have a boolean to say whether or not we have an
    AGN in the ICM.
    :param active - AGN or no AGN
    :param center - physical coordinates of AGN center
    :param radius - radius in arcseconds
    """

    def __init__(self, active):
        self.active = active
        self.x_coord = 0
        self.y_coord = 0
        self.radius = 0

    def set_AGN(self, center_x, center_y, radius):
        self.active = True
        self.x_coord = center_x
        self.y_coord = center_y
        self.radius = radius


# --------------------------Auxilary Functions--------------------------#
def max_counts(image):
    """Maximum counts in image"""
    dmstat.punlearn()
    dmstat.infile = image
    dmstat.centroid = True
    dmstat()
    return int(dmstat.out_max)


def max_coord(image, coord):
    """Maximum coordinate for image"""
    dmstat.punlearn()
    dmstat.infile = image + "[cols " + coord + "]"
    dmstat()
    return float(dmstat.out_max)


def min_coord(image, coord):
    """Minimum coordinate for image"""
    dmstat.punlearn()
    dmstat.infile = image + "[cols " + coord + "]"
    dmstat()
    return float(dmstat.out_min)


# --------------------------Primary Functions--------------------------#
def display_ccds(ccd_list, obsid, Merge=False):
    """
    Display all CCDS together
    PARAMETERS:
        ccd_list - list of ccd numbers
        obsid - current Chandra observation ID
    """
    full_ccd_list = ["ccd" + i for i in ccd_list[obsid]]
    if not full_ccd_list:
        return None if Merge else (None, None)

    sums = {}
    for ccd in full_ccd_list:
        try:
            data = fits.getdata(ccd + ".img")
            data = np.nan_to_num(data, nan=0.0)
            data = np.where(data < 0, 0, data)
            sums[ccd] = float(np.sum(data))
        except Exception:
            sums[ccd] = float("inf")

    bkg_ccd = min(sums, key=lambda ccd: sums[ccd])
    if Merge:
        return bkg_ccd

    src_ccd = max(sums, key=lambda ccd: sums[ccd])
    return bkg_ccd, src_ccd


def display_entire(home_dir, OBSID, repro_img):
    """
    Display normal image from reprocessed Chandra data
    PARAMETERS:
        home_dir - directory containing Chandra data
        OBSID - current Chandra observation ID
        repro_evt - name of the reprocessed event
    """
    try:
        data = fits.getdata(repro_img)
    except Exception:
        data = None

    if data is None:
        logical_x = 1.0
        logical_y = 1.0
        radius = 1.0
    else:
        data = np.nan_to_num(data, nan=0.0)
        data = np.where(data < 0, 0, data)
        total = float(np.sum(data))
        y_idx, x_idx = np.indices(data.shape)
        if total > 0:
            x_cent = float((x_idx * data).sum() / total)
            y_cent = float((y_idx * data).sum() / total)
        else:
            y_cent, x_cent = np.array(data.shape) / 2.0
        logical_x = x_cent + 1.0
        logical_y = y_cent + 1.0
        radius = 0.45 * float(min(data.shape))

    edge_x = min(logical_x + radius, (data.shape[1] if data is not None else logical_x))
    edge_y = logical_y

    # create empty point source and AGN region files
    ptsrc_file = open("pt_srcs.reg", "w+")
    ptsrc_file.write("# Region file format: DS9 version 4.1 \n")
    ptsrc_file.write("image \n")
    agn_ = AGN(False)
    agn_file = open("AGN.reg", "w+")
    agn_file.write("# Region file format: DS9 version 4.1 \n")
    agn_file.write("image \n")
    agn_file.close()
    ptsrc_file.close()
    # move to background directory for later
    copyfile("pt_srcs.reg", home_dir + "/" + OBSID + "/Background/pt_srcs.reg")
    return edge_x, edge_y, agn_


def display_merge(merged_dir, merged_img):
    """
    Display normal image from reprocessed Chandra data after merge
    PARAMETERS:
        merged_dir - directory containing merged Chandra data
        merged_evt - merged event file name
    """
    os.chdir(merged_dir)
    try:
        data = fits.getdata(merged_img)
    except Exception:
        data = None

    if data is None:
        logical_x = 1.0
        logical_y = 1.0
        radius = 1.0
    else:
        data = np.nan_to_num(data, nan=0.0)
        data = np.where(data < 0, 0, data)
        total = float(np.sum(data))
        y_idx, x_idx = np.indices(data.shape)
        if total > 0:
            x_cent = float((x_idx * data).sum() / total)
            y_cent = float((y_idx * data).sum() / total)
        else:
            y_cent, x_cent = np.array(data.shape) / 2.0
        logical_x = x_cent + 1.0
        logical_y = y_cent + 1.0
        radius = 0.45 * float(min(data.shape))

    edge_x = min(logical_x + radius, (data.shape[1] if data is not None else logical_x))
    edge_y = logical_y

    ptsrc_file = open("pt_srcs.reg", "w+")
    ptsrc_file.write("# Region file format: DS9 version 4.1 \n")
    ptsrc_file.write("image \n")
    agn_ = AGN(False)
    agn_file = open("AGN.reg", "w+")
    agn_file.write("# Region file format: DS9 version 4.1 \n")
    agn_file.write("image \n")
    agn_file.close()
    ptsrc_file.close()
    return edge_x, edge_y, agn_
