import matplotlib.pyplot as plt
import numpy as np
from astropy.convolution import Gaussian2DKernel, convolve
from astropy.io import fits
from astropy.wcs import WCS
from ciao_contrib.runtool import dmcoords


def create_src_img(repro_img, centrd, edge):
    """
    Create background-subtracted image with centroid marked and write bkg.reg.
    """
    dmcoords.punlearn()
    dmcoords.infile = repro_img
    dmcoords.option = "cel"
    dmcoords.celfmt = "hms"
    dmcoords.ra = centrd[0]
    dmcoords.dec = centrd[1]
    dmcoords()
    cen_x = dmcoords.x
    cen_y = dmcoords.y
    cen_logx = dmcoords.logicalx
    cen_logy = dmcoords.logicaly

    dmcoords.punlearn()
    dmcoords.infile = repro_img
    dmcoords.option = "cel"
    dmcoords.celfmt = "hms"
    dmcoords.ra = edge[0]
    dmcoords.dec = edge[1]
    dmcoords()
    edge_x = dmcoords.x
    edge_y = dmcoords.y

    hdu = fits.open(repro_img)[0]
    wcs = WCS(hdu.header)
    max_rad = np.sqrt(
        (float(cen_x) - float(edge_x)) ** 2 + (float(cen_y) - float(edge_y)) ** 2
    )
    max_rad = 0.492 * max_rad  # convert to arcsec from physical/sky units
    ax = plt.subplot(projection=wcs)
    image_data = fits.getdata(repro_img)
    kernel = Gaussian2DKernel(x_stddev=3)
    astropy_conv = convolve(image_data, kernel)
    scaled = np.log1p(np.clip(astropy_conv, 0, None))
    vmax = np.percentile(scaled, 99.5) if np.any(scaled) else 1.0
    ax.imshow(
        scaled,
        cmap="magma",
        vmin=0,
        vmax=vmax,
    )
    circle = plt.Circle(
        (cen_logx, cen_logy), max_rad, color="#47f5ff", linewidth=1.6, fill=False
    )
    ax.add_artist(circle)
    plt.xlabel("RA J2000")
    plt.ylabel("DEC J2000")
    plt.savefig("bkgsub_exp.png", bbox_inches="tight")

    with open("bkg.reg", "w+") as reg_bkg:
        reg_bkg.write("# Region file format: DS9 version 4.1 \n")
        reg_bkg.write("physical \n")
        reg_bkg.write(
            'annulus(%s,%s,%f"' % (centrd[0], centrd[1], 1.1 * max_rad)
            + ",%f" % (1.5 * max_rad)
            + '")'
        )
    return None
