import matplotlib.pyplot as plt
import numpy as np
from astropy.convolution import Gaussian2DKernel, convolve
from astropy.io import fits
from astropy.visualization import AsinhStretch, ImageNormalize
from astropy.wcs import WCS
from ciao_contrib.runtool import dmcoords


def create_src_img(repro_img, centrd, edge):
    """
    Create background-subtracted image and write bkg.reg.
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
    # Robust stretch: preserve diffuse structure while limiting bright-point blowout.
    kernel = Gaussian2DKernel(x_stddev=2)
    astropy_conv = convolve(image_data, kernel)
    finite = np.isfinite(astropy_conv)
    positive = astropy_conv[finite & (astropy_conv > 0)]
    if positive.size:
        vmin = float(np.percentile(positive, 5.0))
        vmax = float(np.percentile(positive, 99.7))
        if vmax <= vmin:
            vmin = float(np.min(positive))
            vmax = float(np.max(positive))
    else:
        vmin = 0.0
        vmax = 1.0
    norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch(a=0.08), clip=True)
    ax.imshow(
        np.nan_to_num(astropy_conv, nan=0.0, posinf=vmax, neginf=0.0),
        cmap="magma",
        norm=norm,
    )
    # Keep max_rad for bkg.reg calculation, but do not overlay circles on the PNG.
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
