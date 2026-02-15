from SurfaceBrightness.Coeff_SB import CSB_calc
from SurfaceBrightness.CSB_bounds_merged import calculate_bounds
from SurfaceBrightness.SBProfile import SB_profile


def run_surface_brightness(
    inputs, filenames, cen_ra, cen_dec, cluster_id, db_service, merge_bool
):
    if inputs["surface_brightness_calc"].lower() != "true":
        return

    print("#-----Surface Brightness Mode----#")
    SB_profile(
        inputs["home_dir"] + "/" + inputs["name"] + "/SurfaceBrightness/",
        filenames["evt2_repro"],
        filenames["exp_map"],
        filenames["bkg"],
        cen_ra,
        cen_dec,
        inputs["redshift"],
    )
    print("Calculating Surface Brightess Coefficient")
    CSB_calc(
        inputs["home_dir"],
        inputs["name"],
        inputs["dir_list"],
        cen_ra,
        cen_dec,
        filenames["bkg"],
        inputs["redshift"],
        merge_bool,
    )
    calculate_bounds(
        db_service.mydb,
        db_service.mycursor,
        cluster_id,
        inputs["home_dir"] + "/" + inputs["name"] + "/SurfaceBrightness",
        inputs["name"],
    )
