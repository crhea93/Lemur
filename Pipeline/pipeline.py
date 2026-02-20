"""
PIPELINE FOR TEMPERATURE PROFILE:
The following program will handle all automation of the creation of the
temperature pipeline. The input is handle through an input file so that the user
does not need to change this file.

The program should read run as the following:
python pipeline.py input.i #
where # is the number of values in the input file

INPUT PARAMETERS:
    home_dir -- Directory containing Chandra Data (e.g. '/home/user/Documents/Chandra')
    dir_list -- List of OBSIDS (e.g. ['15173'])
    debug -- If set to True then we are using OBSID 15173 (Abell 85 or Abell 133). Normally set to False :)


VERSIONS (and submission date):
v0 - 01/11/19 - basic pipeline for single observations
v1 - 04/11/19 - fully functioning pipeline for single/multiple observations
v1.1 - 04/25/19 - Considerably more modular and addition of AGN and surface brightness calculations
v1.2 - 05/24/19 - Added cooling radii calculations, coefficient calculations, and moved to a database structure

For suggestions/comments/errata please contact:
Carter Rhea
carter.rhea@umontreal.ca
"""

# ------------------------------------IMPORTS-----------------------------------#
# ----------------------------------GENERAL IMPORTS-----------------------------#
import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from ciao_contrib.runtool import *
from config import load_config, resolve_db_password
from context import PipelineContext
from db import connect_db

# ---------------------------------DATABASE IMPORTS-----------------------------#
from db_service import DatabaseService
from imaging import create_src_img
from Misc.R_cool import R_cool_calc
from preprocessing import (
    generate_ccds,
    init_cluster,
    run_merge_observations,
    run_single_observation,
)
from surface_brightness import run_surface_brightness
from web_export import export_web

# ------------------------------------------------------------------------------#
DB_PASSWORD = "ILoveLuci3!"


# ------------------------------------PROGRAM-----------------------------------#
def _first_float(text):
    match = re.search(r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def _extract_redshift_from_text(text):
    """
    Parse redshift from service text output with conservative matching.
    Avoids grabbing unrelated numbers (e.g. quality flags like '2').
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        low = line.lower()
        if "redshift" not in low:
            continue
        if "quality" in low:
            continue

        # Most robust: Redshift: <value> or Redshift = <value>
        match = re.search(
            r"redshift\s*[:=]\s*([+\-]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        value = _first_float(match.group(1))
        if value is None:
            continue
        # Guard against obvious mis-parse values from metadata lines.
        if value < 0 or value > 5:
            continue
        return value
    return None


def _fetch_text(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "LemurPipeline/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _redshift_from_ned(cluster_name):
    quoted = urllib.parse.quote(cluster_name)
    candidates = [
        f"https://ned.ipac.caltech.edu/byname?objname={quoted}&extend=no&of=pre_text",
        f"https://ned.ipac.caltech.edu/byname?objname={quoted}&extend=no&of=xml_all",
    ]
    for url in candidates:
        try:
            text = _fetch_text(url)
        except Exception:
            continue
        value = _extract_redshift_from_text(text)
        if value is not None:
            return value
        xml_match = re.search(
            r"<redshift>\s*([+\-]?\d+(?:\.\d+)?)\s*</redshift>",
            text,
            flags=re.IGNORECASE,
        )
        if xml_match:
            value = _first_float(xml_match.group(1))
            if value is not None and 0 <= value <= 5:
                return value
    return None


def _redshift_from_cds(cluster_name):
    quoted = urllib.parse.quote(cluster_name)
    candidates = [
        f"https://simbad.u-strasbg.fr/simbad/sim-id?Ident={quoted}&output.format=ASCII",
        f"https://simbad.cds.unistra.fr/simbad/sim-id?Ident={quoted}&output.format=ASCII",
    ]
    for url in candidates:
        try:
            text = _fetch_text(url)
        except Exception:
            continue
        value = _extract_redshift_from_text(text)
        if value is not None:
            return value
    return None


def resolve_redshift(cluster_name):
    redshift = _redshift_from_ned(cluster_name)
    if redshift is not None:
        print(f"Resolved redshift from NED: {redshift}")
        return redshift
    redshift = _redshift_from_cds(cluster_name)
    if redshift is not None:
        print(f"Resolved redshift from CDS: {redshift}")
        return redshift
    raise RuntimeError(
        f"Unable to resolve redshift for '{cluster_name}' from NED or CDS. "
        "Pass --redshift explicitly."
    )


def parse_obsids(obsid_args):
    obsids = []
    for raw in obsid_args:
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            if not value.isdigit():
                raise ValueError(f"Invalid OBSID '{value}'. OBSIDs must be integers.")
            obsids.append(value)
    unique = []
    for obsid in obsids:
        if obsid not in unique:
            unique.append(obsid)
    if not unique:
        raise ValueError("No OBSIDs provided.")
    return unique


def load_inputs_from_cli(cluster_name, obsid_args, defaults_path, redshift_override):
    inputs, _, env_vars = load_config(defaults_path)
    obsids = parse_obsids(obsid_args)
    if redshift_override is not None:
        redshift = float(redshift_override)
    else:
        try:
            redshift = resolve_redshift(cluster_name)
        except Exception as exc:
            fallback = inputs.get("redshift", 0.0)
            redshift = float(fallback)
            print(
                "WARNING: redshift lookup failed for "
                f"'{cluster_name}' ({exc}). Using fallback redshift={redshift}."
            )
    inputs["name"] = cluster_name
    inputs["dir_list"] = obsids
    inputs["merge"] = "True" if len(obsids) > 1 else "False"
    inputs["redshift"] = float(redshift)
    merge_bool = len(obsids) > 1
    return inputs, merge_bool, env_vars


def run_pipeline_with_config(inputs, merge_bool, env_vars):
    # ---------------------------Global Imports--------------------------------#
    global max_rad, cen_x, cen_y, edge_x, edge_y, filenames, annuli_data
    global Temperatures, Abundances, Norms, Fluxes, obsid_, main_out
    global Temp_min, Temp_max, Ab_min, Ab_max, Norm_min, Norm_max
    global mydb, mycursor
    # ---------------------------Read in data----------------------------------#
    db_password = resolve_db_password(inputs, env_vars, DB_PASSWORD)
    mydb, mycursor, db_user, db_host, db_name = connect_db(inputs, db_password)
    ctx = PipelineContext(
        inputs=inputs,
        merge_bool=merge_bool,
        db_user=db_user,
        db_password=db_password,
        db_host=db_host,
        db_name=db_name,
        mydb=mydb,
        mycursor=mycursor,
    )
    db_service = DatabaseService(
        ctx.mydb,
        ctx.mycursor,
        ctx.db_user,
        ctx.db_password,
        ctx.db_host,
        ctx.db_name,
    )

    print("#-------STARTING ANALYSIS ON %s-------#" % ctx.inputs["name"])
    os.chdir(ctx.inputs["home_dir"])
    db_service.add_cluster(ctx.inputs["name"], ctx.inputs["redshift"])
    main_out = init_cluster(ctx.inputs)
    ccds = generate_ccds(ctx.inputs)

    if ctx.merge_bool == False:
        filenames, cen_ra, cen_dec, edge_ra, edge_dec, agn_ = run_single_observation(
            ctx.inputs, ccds, main_out, db_service
        )
    else:
        filenames, cen_ra, cen_dec, edge_ra, edge_dec, agn_ = run_merge_observations(
            ctx.inputs, ccds, main_out, db_service
        )

    filenames["exp_corr"] = (
        ctx.inputs["home_dir"] + "/" + ctx.inputs["name"] + "/broad_flux.img"
    )  # Need this defined
    # Calculate additional needed parameters
    create_src_img(filenames["exp_corr"], [cen_ra, cen_dec], [edge_ra, edge_dec])
    db_service.add_coord(ctx.inputs["name"], cen_ra, cen_dec)
    # Get cluster ID
    cluster_id = db_service.get_id(ctx.inputs["name"])

    # ----------------------------------Surface Brightness------------------------------------------#
    os.chdir(ctx.inputs["home_dir"] + "/" + ctx.inputs["name"])
    filenames["exp_map"] = os.getcwd() + "/broad_thresh.expmap"
    filenames["bkg"] = os.getcwd() + "/bkg.reg"
    run_surface_brightness(
        ctx.inputs, filenames, cen_ra, cen_dec, cluster_id, db_service, ctx.merge_bool
    )

    # ---------------------------------Additional Calculations--------------------------------------#
    R_cool_calc(
        ctx.mydb,
        ctx.mycursor,
        cluster_id,
        ctx.inputs["name"],
        ctx.inputs["home_dir"] + "/" + ctx.inputs["name"] + "/Fits",
        ctx.inputs["redshift"],
        main_out,
    )

    # --------------------------FINISH---------------------------------#
    export_web(ctx.inputs)
    db_service.update_api_db(ctx.inputs)
    main_out.close()
    return None


def run_pipeline(input_path):
    inputs, merge_bool, env_vars = load_config(input_path)
    return run_pipeline_with_config(inputs, merge_bool, env_vars)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Run pipeline from input file, or from --cluster + --obsids with "
            "defaults and auto redshift lookup (NED/CDS)."
        )
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        help="Path to traditional .i input file (legacy mode).",
    )
    parser.add_argument(
        "--cluster",
        help="Cluster name (new mode). Requires --obsids.",
    )
    parser.add_argument(
        "--obsids",
        nargs="+",
        help=(
            "OBSID list for new mode. Supports comma separated and/or spaced "
            "values, e.g. --obsids 2203,9897 or --obsids 2203 9897."
        ),
    )
    parser.add_argument(
        "--defaults",
        default=str(Path(__file__).resolve().parent.parent / "inputs" / "template.i"),
        help="Path to defaults .i file for new mode.",
    )
    parser.add_argument(
        "--redshift",
        type=float,
        help="Optional redshift override for new mode (skips NED/CDS lookup).",
    )
    args = parser.parse_args(argv)

    using_legacy = bool(args.input_path)
    using_new = bool(args.cluster or args.obsids)
    if using_legacy and using_new:
        parser.error(
            "Use either positional input_path OR --cluster/--obsids, not both."
        )
    if not using_legacy and not using_new:
        parser.error("Provide input_path or use --cluster with --obsids.")
    if using_new and (not args.cluster or not args.obsids):
        parser.error("New mode requires both --cluster and --obsids.")
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.input_path:
        return run_pipeline(args.input_path)
    inputs, merge_bool, env_vars = load_inputs_from_cli(
        cluster_name=args.cluster,
        obsid_args=args.obsids,
        defaults_path=args.defaults,
        redshift_override=args.redshift,
    )
    return run_pipeline_with_config(inputs, merge_bool, env_vars)


if __name__ == "__main__":
    main()
