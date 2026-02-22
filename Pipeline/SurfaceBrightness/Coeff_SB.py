"""
Surface Brightness Coefficient Calculation
"""

import os
from shutil import copy, copyfile

from astropy.io import fits
from ciao_contrib.runtool import *
from Misc.ASCalc import angle_calc
from pycrates import *

# ------------------------------------------------------------------------------#
# ------------------------------------------------------------------------------#


def calc_effenergy(region, energy_range2):
    dmtcalc.infile = region + ".arf"
    dmtcalc.outfile = "arf_weights" + str(region) + ".arf"
    dmtcalc.expression = (
        "mid_energy=(energ_lo+energ_hi)/2.0;weights=(mid_energy*specresp)"
    )
    dmtcalc.clobber = True
    dmtcalc()
    dmstat.infile = (
        "arf_weights"
        + str(region)
        + ".arf[mid_energy="
        + str(energy_range2)
        + "][cols weights]"
    )
    dmstat.verbose = True
    dmstat()
    weight_sum = float(dmstat.out_sum)
    dmstat.infile = (
        "arf_weights"
        + str(region)
        + ".arf[mid_energy="
        + str(energy_range2)
        + "][cols specresp]"
    )
    dmstat.verbose = True
    dmstat()
    specresp_sum = float(dmstat.out_sum)
    eff_energy = weight_sum / specresp_sum
    return eff_energy


def calc_flux(evt_file, merged_obs, energy_range, region, background, exposure=False):
    # Rearrange energy ranges
    energies = [float(x) for x in energy_range.split(":")]
    (
        str(energies[0] / 1000) + ":" + str(energies[1] / 1000)
    )  # for effective energy (eV)
    energy_range3 = (
        str(energies[0] / 1000) + "-" + str(energies[1] / 1000)
    )  # For average effective exposures (eV)
    # Get counts for region and background
    dmextract.infile = (
        evt_file
        + ".fits[energy="
        + energy_range
        + "][bin sky=region("
        + region
        + ".reg)]"
    )
    dmextract.outfile = region + "_counts.fits"
    dmextract.opt = "generic"
    # dmextract.infile = evt_file+".fits[energy="+energy_range+"][bin sky=region("+region+".reg)]"
    dmextract.bkg = (
        evt_file
        + ".fits[energy="
        + energy_range
        + "][bin sky=region("
        + background
        + ")]"
    )
    dmextract.clobber = True
    dmextract()
    dmstat.infile = region + "_counts.fits[cols counts]"
    dmstat()
    counts = float(dmstat.out_sum)
    dmstat.infile = region + "_counts.fits[cols area]"
    dmstat()
    area = float(dmstat.out_sum)
    dmstat.infile = region + "_counts.fits[cols bg_counts]"
    dmstat()
    bg_counts = float(dmstat.out_sum)
    dmstat.infile = region + "_counts.fits[cols bg_area]"
    dmstat()
    bg_area = float(dmstat.out_sum)
    # Exposure Time
    # Set PSF elements
    alpha = 1  # PSF fraction in source aperature; 1-perfect
    beta = 0  # PSF fraction in background aperature; 0-perfect
    # Exposure Time
    T_s = 0
    T_b = 0
    for obsid in merged_obs:
        hdu = fits.open(obsid + ".fits")
        hdr = hdu[0].header
        T_s += hdr["TSTOP"] - hdr["TSTART"]
        T_b += T_s
        hdu.close()
    # Calculate average effective exposures
    dmstat.punlearn()
    dmstat.infile = (
        obsid + "_" + energy_range3 + "_thresh.expmap[sky=region(" + region + ".reg)]"
    )
    dmstat.centroid = False
    dmstat()
    E_s = float(dmstat.out_mean)
    dmstat.punlearn()
    dmstat.infile = (
        obsid + "_" + energy_range3 + "_thresh.expmap[sky=region(" + background + ")]"
    )
    dmstat.centroid = False
    dmstat()
    E_b = float(dmstat.out_mean)
    # Calculate average photon energies in source and background aperature
    if not exposure:
        dmtcalc.punlearn()
        dmtcalc.infile = (
            evt_file
            + ".fits[energy="
            + energy_range
            + ",sky=region("
            + region
            + ".reg)]"
        )
        dmtcalc.outfile = region + "_source_energy.fits"
        dmtcalc.expression = "energy=1.6e-12*energy"  # Convert to ergs
        dmtcalc.clobber = True
        dmtcalc()
        dmstat.punlearn()
        dmstat.infile = region + "_source_energy.fits[cols energy]"
        dmstat()
        eng_s = float(dmstat.out_mean)
        dmtcalc.punlearn()
        dmtcalc.infile = (
            evt_file
            + ".fits[energy="
            + energy_range
            + ",sky=region("
            + background
            + ")]"
        )
        dmtcalc.outfile = region + "_background_energy.fits"
        dmtcalc.expression = "energy=1.6e-12*energy"  # Convert to ergs
        dmtcalc.clobber = True
        dmtcalc()
        dmstat.punlearn()
        dmstat.infile = region + "_background_energy.fits[cols energy]"
        dmstat()
        eng_b = float(dmstat.out_mean)
        # set flux_s,flux_b to zero to ignore exposure
        flux_s = 1
        flux_b = 1
    if exposure:
        eff2evt.punlearn()
        eff2evt.infile = (
            evt_file
            + ".fits[energy="
            + energy_range
            + "][sky=region("
            + region
            + ".reg)]"
        )
        eff2evt.outfile = region + "_source_effexp.fits"
        eff2evt.clobber = True
        eff2evt()
        dmstat.punlearn()
        dmstat.infile = region + "_source_effexp.fits[cols flux]"
        dmstat()
        flux_s = float(dmstat.out_mean)
        eff2evt.punlearn()
        eff2evt.infile = (
            evt_file
            + ".fits[energy="
            + energy_range
            + "][sky=region("
            + background
            + ")]"
        )
        eff2evt.outfile = region + "_background_effexp.fits"
        eff2evt.clobber = True
        eff2evt()
        dmstat.punlearn()
        dmstat.infile = region + "_background_effexp.fits[cols flux]"
        dmstat()
        flux_b = float(dmstat.out_mean)
        # Conversely set eng_s,eng_b to one to signify we are using effective exposure
        eng_s = 1
        eng_b = 1

    # Calculate energy flux and bounds
    aprates.punlearn()
    aprates.conf = 0.90
    aprates.n = counts
    aprates.m = bg_counts
    aprates.A_s = area
    aprates.A_b = bg_area
    aprates.alpha = alpha
    aprates.beta = beta
    aprates.T_s = T_s
    aprates.T_b = T_b
    aprates.E_s = E_s
    aprates.E_b = E_b
    aprates.eng_s = eng_s
    aprates.eng_b = eng_b
    aprates.flux_s = flux_s
    aprates.flux_b = flux_b
    aprates.outfile = "aprates_" + region + ".par"
    aprates.clobber = True
    aprates.pdf = "alternate"
    aprates()

    return None


def create_arf(directory_base, obs_to_merge, region, out_dir):
    # Create arf files
    arf_files = ""
    pi_files = ""
    for obsid in obs_to_merge:
        arf_files += directory_base + "/" + obsid + "/repro/" + region + ".arf,"
        pi_files += directory_base + "/" + obsid + "/repro/" + region + ".pi,"
    arf_files = arf_files[:-1]  # get rid of final comma
    pi_files = pi_files[:-1]
    addresp.punlearn()
    addresp.infile = ""
    addresp.arffile = arf_files
    addresp.phafile = pi_files
    addresp.outfile = ""
    addresp.outarf = out_dir + "/" + region + ".arf"
    addresp.clobber = True
    addresp()


def spec_run(directory_base, obsid, region, energy_range, bkg_file):
    """
    Create spectra for region file in obserservation in soft band
    """
    os.chdir(directory_base + "/" + obsid + "/repro")
    evt_file = "acisf" + obsid + "_repro_evt2"
    specextract.punlearn()
    specextract.infile = (
        evt_file + ".fits[energy=" + energy_range + "][sky=region(" + region + ".reg)]"
    )
    specextract.outroot = region + "_"
    specextract.bkgfile = evt_file + ".fits[sky=region(" + bkg_file + ")]"
    specextract.bkgresp = False
    specextract.clobber = True
    specextract()


def merge_observations(
    obs_to_merge, output_dir, directory_base, energy_range2, mono_energy
):
    # Merge individual region files
    merging_files = ""
    for obsid in obs_to_merge:
        merging_files += (
            directory_base + "/" + obsid + "/repro/acisf" + obsid + "_repro_evt2.fits,"
        )
    merging_files = merging_files[:-1]
    merge_obs.punlearn()
    merge_obs.infile = merging_files
    merge_obs.outroot = output_dir + "/"
    merge_obs.bands = energy_range2 + ":" + str(mono_energy)
    merge_obs.clobber = True
    merge_obs()


def CSB_calc(
    directory_base, dir_name, obs, cen_ra, cen_dec, bkg_file, redshift, merge_bool
):
    os.chdir(directory_base + "/" + dir_name)
    regions = ["40kpc", "400kpc"]
    sizes = [40, 400]
    energy_range = "500:2000"  # Soft range in electron volts
    # Create Region files and combine arfs
    ct = 0
    for region in regions:
        print(" Region " + region + "...")
        reg_size = angle_calc(redshift, sizes[ct])
        with open(region + ".reg", "w+") as new_reg:
            new_reg.write("# Region file format: DS9 version 4.1 \n")
            new_reg.write("physical \n")
            new_reg.write(
                "circle(" + cen_ra + "," + cen_dec + "," + str(reg_size) + '"' + ")"
            )
        for obsid in obs:
            try:
                copy(bkg_file, directory_base + "/" + obsid + "/repro")
            except Exception:
                pass
            try:
                copy(region + ".reg", directory_base + "/" + obsid + "/repro")
            except Exception:
                pass
            spec_run(directory_base, obsid, region, energy_range, bkg_file)
        create_arf(
            directory_base,
            obs,
            region,
            directory_base + "/" + dir_name + "/SurfaceBrightness",
        )
        copyfile(
            region + ".reg",
            directory_base + "/" + dir_name + "/SurfaceBrightness/" + region + ".reg",
        )
        ct += 1
    # Move to merged directory
    os.chdir(directory_base + "/" + dir_name + "/SurfaceBrightness")
    energies = [float(x) for x in energy_range.split(":")]
    energy_range2 = str(energies[0] / 1000) + ":" + str(energies[1] / 1000)
    mono_energy = calc_effenergy(region, energy_range2)
    merge_observations(
        obs,
        directory_base + "/" + dir_name + "/SurfaceBrightness/",
        directory_base,
        energy_range2,
        mono_energy,
    )

    for obser in obs:
        copyfile(
            directory_base + "/" + obser + "/repro/acisf" + obser + "_repro_evt2.fits",
            directory_base + "/" + dir_name + "/SurfaceBrightness/" + obser + ".fits",
        )
    for region in regions:
        print(" Calculating flux for " + region)
        calc_flux("merged_evt", obs, energy_range, region, bkg_file, exposure=False)
    return None
