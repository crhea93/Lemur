"""
Search for flares in data before reprocessing
"""

import os

from ciao_contrib.runtool import *


def Flares(flare_gti, base_dir, output_dir, filenames):
    """
    Search for flares in data before reprocessing
    PARAMETERS:
        flare_gti - background flare gti file
        base_dir - chandra observation directory
        output_dir - name of reprocessed-data directory
        filenames - dictionary of files
    """
    os.chdir(os.getcwd() + "/Background")
    # Determine Goodtime intervals
    evt1_name = filenames["evt1"].split(".")[0]
    output_evt1_deflared = (
        base_dir + "/" + output_dir + "/" + evt1_name.split("/")[-1] + "_deflared.fits"
    )
    dmcopy.punlearn()
    dmcopy.clobber = True
    dmcopy.outfile = output_evt1_deflared
    try:
        dmcopy.infile = evt1_name + ".fits[@" + flare_gti + "]"
        dmcopy()
    except Exception as exc:
        # Missing/invalid GTI should not abort long reduction batches.
        print(
            f"WARNING: flare GTI filtering failed for {evt1_name}. "
            "Proceeding without flare filtering for this OBSID. "
            f"Error: {exc}"
        )
        dmcopy.punlearn()
        dmcopy.clobber = True
        dmcopy.infile = evt1_name + ".fits"
        dmcopy.outfile = output_evt1_deflared
        dmcopy()
    # filenames['evt1'].split('.')[1] == .fits
    filenames["evt1_deflared"] = (
        base_dir
        + "/"
        + output_dir
        + "/"
        + evt1_name.split("/")[-1]
        + "_deflared."
        + filenames["evt1"].split(".")[1]
    )
    # Clear status bits for future cleaning
    os.system("acis_clear_status_bits " + filenames["evt1_deflared"])
    return None
