"""
Calculate Centroid
"""

import numpy as np
from astropy.io import fits
from ciao_contrib.runtool import *


def _logical_centroid(image_path):
    try:
        data = fits.getdata(image_path)
    except Exception:
        data = None

    if data is None:
        return 1.0, 1.0

    data = np.nan_to_num(data, nan=0.0)
    data = np.where(data < 0, 0, data)
    total = float(np.sum(data))
    y_idx, x_idx = np.indices(data.shape)
    if total > 0:
        x_cent = float((x_idx * data).sum() / total)
        y_cent = float((y_idx * data).sum() / total)
    else:
        y_cent, x_cent = np.array(data.shape) / 2.0

    return x_cent + 1.0, y_cent + 1.0


def basic_centroid_guess(ccd_src):
    """
    Initial Guess of the X-ray centroid
    PARAMETERS:
        ccd_src - CCD number that contains source
    """
    dmstat.punlearn()
    dmstat.infile = ccd_src + ".img"
    dmstat.centroid = True
    dmstat()
    # print(dmstat.out_max_loc.split(','))
    return dmstat.out_cntrd_phys.split(",")[0], dmstat.out_cntrd_phys.split(",")[1]


def basic_centroid(ccd_src):
    """
    Final choice of centroid
    PARAMETERS:
        ccd_src - CCD number that contains source
    """
    logical_x, logical_y = _logical_centroid(ccd_src + ".img")
    dmcoords.punlearn()
    dmcoords.infile = ccd_src + ".img"
    dmcoords.option = "logical"
    dmcoords.logicalx = logical_x
    dmcoords.logicaly = logical_y
    dmcoords()
    return dmcoords.ra, dmcoords.dec


def merged_centroid(merged_img):
    """
    Final choice of centroid in merged observations
    PARAMETERS:
        merged_file - img file for merged observations without extensions
    OUTPUT IN PHYSICAL UNITS
    """

    logical_x, logical_y = _logical_centroid(merged_img)
    dmcoords.punlearn()
    dmcoords.infile = merged_img
    dmcoords.option = "logical"
    dmcoords.logicalx = logical_x
    dmcoords.logicaly = logical_y
    dmcoords()
    return dmcoords.ra, dmcoords.dec
