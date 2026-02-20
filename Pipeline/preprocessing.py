import os

from ciao_contrib.runtool import *
from Misc.Bkg_sub import create_clean_img, create_clean_img_merge, run_bkg_sub
from Misc.filenames import get_filenames
from Misc.move import move_files
from Misc.RaDec import get_RaDec_log
from Preliminary.CCD_split import split_ccds
from Preliminary.Centroid import basic_centroid, basic_centroid_guess, merged_centroid
from Preliminary.chips_ccd import AGN, display_ccds, display_entire, display_merge
from Preliminary.CreateLightcurves import bkg_clean_srcs, bkg_lightcurve
from Preliminary.FaintCleaning import FaintCleaning
from Preliminary.Merge import merge_objects
from Preliminary.unzip import unzip


def init_cluster(inputs):
    os.chdir(inputs["home_dir"])
    if not os.path.exists(inputs["home_dir"] + "/" + inputs["name"]):
        os.makedirs(inputs["home_dir"] + "/" + inputs["name"])
    main_out = open(inputs["home_dir"] + "/" + inputs["name"] + "/Additional.txt", "w+")
    return main_out


def generate_ccds(inputs):
    unzip(inputs["home_dir"], inputs["dir_list"])
    print("Generating fits and image files for each individual CCD...")
    return split_ccds(inputs["home_dir"], inputs["dir_list"])


def run_single_observation(inputs, ccds, main_out, db_service):
    print("#-----Single Observation Mode----#")
    agn_ = AGN(False)
    filenames = {}
    cen_ra = cen_dec = edge_ra = edge_dec = None

    for obsid_ in inputs["dir_list"]:
        db_service.add_obsid(inputs["name"], obsid_)
        main_out_obsid = open(
            inputs["home_dir"] + "/" + obsid_ + "/decisions.txt", "w+"
        )
        os.chdir(os.getcwd() + "/" + obsid_ + "/Background")
        print("    Now let us pick our src and background ccd...")
        bkg_ccd, src_ccd = display_ccds(ccds, obsid_)
        main_out_obsid.write("The background CCD chosen is CCD#%s\n" % bkg_ccd)
        main_out_obsid.write("The source CCD chosen is CCD#%s\n" % src_ccd)
        if inputs["cleaning"].lower() == "true":
            print("    We can now create a lightcurve for the background...")
            bkg_clean_srcs(bkg_ccd)
            bkg_lightcurve(bkg_ccd, obsid_, create_plot=False)
            cen_x, cen_y = basic_centroid_guess(src_ccd)
            print("    We need to clean our diffuse emission...")
            filenames = FaintCleaning(
                inputs["home_dir"], obsid_, bkg_ccd, cen_x, cen_y, ccds[obsid_]
            )
        if inputs["cleaning"].lower() == "false":
            os.chdir(inputs["home_dir"] + "/" + obsid_)
            filenames, temp = get_filenames()
            filenames["evt2_repro"] = (
                os.getcwd() + "/repro/acisf" + obsid_ + "_repro_evt2.fits"
            )
            os.chdir(inputs["home_dir"] + "/" + obsid_ + "/repro")
        print(
            "    We will now choose the extent of the source and any point sources on the src ccd..."
        )
        fluximage(
            filenames["evt2_repro"],
            inputs["home_dir"] + "/" + inputs["name"] + "/",
            clobber="yes",
        )
        filenames["exp_corr"] = (
            inputs["home_dir"] + "/" + inputs["name"] + "/broad_flux.img"
        )
        edge_x, edge_y, agn_ = display_entire(
            inputs["home_dir"], obsid_, filenames["exp_corr"]
        )
        edge_ra, edge_dec = get_RaDec_log(filenames["exp_corr"], edge_x, edge_y)
        main_out_obsid.write(
            "The edge's X,Y sky coordinates are: %s,%s \n" % (edge_ra, edge_dec)
        )
        os.chdir(inputs["home_dir"] + "/" + obsid_ + "/Background")
        print("    We will now calculate the centroid...")
        cen_ra, cen_dec = basic_centroid(src_ccd)
        main_out_obsid.write(
            "The centroid's X,Y sky coordinates are: %s,%s \n"
            % (str(cen_ra), str(cen_dec))
        )
        if inputs["cleaning"].lower() == "true":
            os.chdir(inputs["home_dir"] + "/" + obsid_ + "/repro")
            print("    Creating Clean Image...")
            create_clean_img(filenames)
            print("    Running Background Subtraction...")
            run_bkg_sub(
                filenames["evt2_repro_uncontam"],
                filenames["evt_uncontam_img"],
                obsid_,
                filenames,
            )
        if inputs["cleaning"].lower() == "false":
            filenames["evt2_repro_uncontam"] = (
                filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
            )
            filenames["evt_bkgsub_img"] = (
                inputs["home_dir"]
                + "/"
                + obsid_
                + "/repro/"
                + obsid_
                + "_blank_particle_bkgsub.img"
            )
            filenames["evt_uncontam_img"] = (
                inputs["home_dir"] + "/" + obsid_ + "/repro/" + "evt_uncontam.img"
            )

        os.chdir(inputs["home_dir"] + "/" + obsid_ + "/repro")
        if not os.path.exists(inputs["home_dir"] + "/" + inputs["name"]):
            os.makedirs(inputs["home_dir"] + "/" + inputs["name"])
        print("Moving Files")
        move_files(inputs["home_dir"] + "/" + inputs["name"], filenames)
        os.chdir(inputs["home_dir"] + "/" + inputs["name"])

    return filenames, cen_ra, cen_dec, edge_ra, edge_dec, agn_


def run_merge_observations(inputs, ccds, main_out, db_service):
    print("#-----Multiple Observation Mode----#")
    print("Beginning cleaning process for each individual obsid...")
    agn_ = AGN(False)
    filenames = {}
    cen_ra = cen_dec = edge_ra = edge_dec = None

    for obsid_ in inputs["dir_list"]:
        db_service.add_obsid(inputs["name"], obsid_)
        if inputs["cleaning"].lower() == "true":
            main_out_obsid = open(
                inputs["home_dir"] + "/" + obsid_ + "/decisions.txt", "w+"
            )
            os.chdir(inputs["home_dir"] + "/" + obsid_ + "/Background")
            print("We are on obsid %s" % obsid_)
            main_out_obsid.write("Obsid %s" % obsid_)
            print("    Now let us pick our background ccd...")
            bkg_ccd = display_ccds(ccds, obsid_, Merge=True)
            main_out_obsid.write("The background CCD chosen is CCD#%s\n" % bkg_ccd)
            print("    We can now create a lightcurve for the background...")
            bkg_clean_srcs(bkg_ccd)
            bkg_lightcurve(bkg_ccd, obsid_, create_plot=False)
            print("    We need to clean our diffuse emission...")
            filenames = FaintCleaning(
                inputs["home_dir"], obsid_, bkg_ccd, 0, 0, ccds[obsid_]
            )
            os.chdir(inputs["home_dir"] + "/" + obsid_ + "/repro")
            print("    Creating Clean Image...")
            create_clean_img_merge(filenames)
            print("    Running Background Subtraction...")
            try:
                run_bkg_sub(
                    filenames["evt2_repro_uncontam"],
                    filenames["evt_uncontam_img"],
                    obsid_,
                    filenames,
                )
            except Exception as exc:
                # Some observations fail blanksky_image due to calibration/grid mismatch.
                # Allow merge workflow to continue using the cleaned image for this OBSID.
                print(
                    f"    WARNING: background subtraction failed for obsid {obsid_}: {exc}"
                )
                print(
                    "    WARNING: continuing with uncontaminated image for this OBSID."
                )
                filenames["evt_bkgsub_img"] = filenames["evt_uncontam_img"]
            main_out_obsid.close()

    if inputs["cleaning"].lower() == "false":
        os.chdir(inputs["home_dir"] + "/" + inputs["dir_list"][0])
        filenames, temp = get_filenames()
        filenames["evt2_repro"] = (
            inputs["home_dir"] + "/" + inputs["name"] + "/merged_evt.fits"
        )
        filenames["evt2_repro_uncontam"] = (
            filenames["evt2_repro"].split(".")[0] + "_uncontam.fits"
        )
        filenames["evt_bkgsub_img"] = (
            inputs["home_dir"] + "/" + inputs["name"] + "/broad_flux.img"
        )
        filenames["evt_uncontam_img"] = (
            inputs["home_dir"] + "/" + inputs["name"] + "/broad_flux.img"
        )

    print("Beginning Merged Calculations...")
    print("    Merging obsids...")
    os.chdir(inputs["home_dir"])
    merge_objects(inputs["dir_list"], inputs["name"], clean="yes")
    os.chdir(inputs["home_dir"] + "/" + inputs["name"])
    filenames["evt2_repro"] = (
        inputs["home_dir"] + "/" + inputs["name"] + "/merged_evt.fits"
    )
    if not os.path.exists(filenames["evt2_repro"]):
        raise RuntimeError(
            "Merged event file was not created: " + filenames["evt2_repro"]
        )
    print("    Choosing extent of source and contaminating point sources")
    edge_x, edge_y, agn_ = display_merge(
        inputs["home_dir"] + "/" + inputs["name"], "broad_flux.img"
    )
    edge_ra, edge_dec = get_RaDec_log("broad_flux.img", edge_x, edge_y)
    main_out.write("The edge point is chosen to be %s,%s \n" % (edge_ra, edge_dec))
    os.chdir(inputs["home_dir"] + "/" + inputs["name"])
    print("    Calculating centroid position")
    cen_ra, cen_dec = merged_centroid("broad_flux.img")
    main_out.write("The center point is chosen to be %s,%s \n" % (cen_ra, cen_dec))

    return filenames, cen_ra, cen_dec, edge_ra, edge_dec, agn_
