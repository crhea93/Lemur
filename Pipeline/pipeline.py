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
from typing import Any

from config import load_config, resolve_db_password

# ------------------------------------------------------------------------------#


# ------------------------------------PROGRAM-----------------------------------#
def _first_float(text):
    match = re.search(r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def _sexagesimal_to_degrees(value, is_ra=False):
    text = str(value).strip()
    match = re.match(
        r"^([+\-]?\d+):(\d+):(\d+(?:\.\d+)?)$",
        text,
    )
    if not match:
        return None

    hours_or_deg = float(match.group(1))
    minutes = float(match.group(2))
    seconds = float(match.group(3))
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        return None

    sign = -1.0 if hours_or_deg < 0 else 1.0
    abs_first = abs(hours_or_deg)
    total = abs_first + minutes / 60.0 + seconds / 3600.0
    if is_ra:
        return total * 15.0
    return sign * total


def _coerce_coord_value(raw, is_ra=False):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = str(raw).strip()
        if not text:
            return None
        parsed = _first_float(text)
        if parsed is None:
            parsed = _sexagesimal_to_degrees(text, is_ra=is_ra)
            if parsed is None:
                return None
        value = float(parsed)
    if is_ra and 0 <= value <= 360:
        return value
    if not is_ra and -90 <= value <= 90:
        return value
    return None


def _extract_fits_value(raw):
    text = str(raw).strip()
    if not text:
        return None
    if "=" in text:
        text = text.split("=", 1)[1].strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        text = text[1:-1].strip()
    return text


def _read_fits_header(path, max_blocks=64):
    header = {}
    with open(path, "rb") as handle:
        for _ in range(max_blocks):
            block = handle.read(2880)
            if not block:
                break
            for offset in range(0, len(block), 80):
                card = block[offset : offset + 80]
                if len(card) < 80:
                    continue
                line = card.decode("ascii", errors="ignore")
                key = line[:8].strip()
                if key == "END":
                    return header
                if not key:
                    continue
                value = _extract_fits_value(line[8:])
                if value is not None:
                    header[key.upper()] = value
    return header


def _coords_from_fits_header(path):
    if not path:
        return None
    try:
        header = _read_fits_header(path)
    except Exception:
        return None

    # CRVAL1/2 are usually the most direct world-coordinate center values.
    for ra_key, dec_key in [
        ("CRVAL1", "CRVAL2"),
        ("RA_NOM", "DEC_NOM"),
        ("RA_OBJ", "DEC_OBJ"),
        ("OBJCTRA", "OBJCTDEC"),
    ]:
        ra_raw = header.get(ra_key)
        dec_raw = header.get(dec_key)
        ra = _coerce_coord_value(ra_raw, is_ra=True)
        dec = _coerce_coord_value(dec_raw, is_ra=False)
        if ra is not None and dec is not None:
            return ra, dec
    return None


def _coords_from_ned(cluster_name):
    quoted = urllib.parse.quote(cluster_name)
    candidates = [
        f"https://ned.ipac.caltech.edu/byname?objname={quoted}&extend=no&of=xml_all",
        f"https://ned.ipac.caltech.edu/byname?objname={quoted}&extend=no&of=pre_text",
    ]
    for url in candidates:
        try:
            text = _fetch_text(url)
        except Exception:
            continue
        ra_match = re.search(r"<ra>\s*([+\-]?\d+(?:\.\d+)?)\s*</ra>", text, re.I)
        dec_match = re.search(r"<dec>\s*([+\-]?\d+(?:\.\d+)?)\s*</dec>", text, re.I)
        if ra_match and dec_match:
            ra = _coerce_coord_value(ra_match.group(1), is_ra=True)
            dec = _coerce_coord_value(dec_match.group(1), is_ra=False)
            if ra is not None and dec is not None:
                return ra, dec
    return None


def _coords_from_cds(cluster_name):
    quoted = urllib.parse.quote(cluster_name)
    candidates = [
        f"https://cds.unistra.fr/cgi-bin/nph-sesame/-oI/SNV?{quoted}",
        f"https://cds.u-strasbg.fr/cgi-bin/nph-sesame/-oI/SNV?{quoted}",
    ]
    for url in candidates:
        try:
            text = _fetch_text(url)
        except Exception:
            continue
        for line in text.splitlines():
            clean = line.strip()
            if not clean.startswith("%J"):
                continue
            parts = clean[2:].strip().split()
            if len(parts) < 2:
                continue
            ra = _coerce_coord_value(parts[0], is_ra=True)
            dec = _coerce_coord_value(parts[1], is_ra=False)
            if ra is not None and dec is not None:
                return ra, dec
    return None


def resolve_coordinates(cluster_name, fallback_fits_paths=None):
    coords = _coords_from_ned(cluster_name)
    if coords is not None:
        print(f"Resolved coordinates from NED: RA={coords[0]} DEC={coords[1]}")
        return coords

    coords = _coords_from_cds(cluster_name)
    if coords is not None:
        print(f"Resolved coordinates from CDS: RA={coords[0]} DEC={coords[1]}")
        return coords

    for candidate in fallback_fits_paths or []:
        coords = _coords_from_fits_header(candidate)
        if coords is not None:
            print(
                "Resolved coordinates from FITS header "
                f"({candidate}): RA={coords[0]} DEC={coords[1]}"
            )
            return coords
    return None


def choose_coordinates(cluster_name, cen_ra, cen_dec, fallback_fits_paths=None):
    ra = _coerce_coord_value(cen_ra, is_ra=True)
    dec = _coerce_coord_value(cen_dec, is_ra=False)
    if ra is not None and dec is not None:
        return ra, dec
    resolved = resolve_coordinates(
        cluster_name, fallback_fits_paths=fallback_fits_paths
    )
    if resolved is not None:
        return resolved
    return None, None


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
    from context import PipelineContext
    from db import connect_db
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

    # ---------------------------Read in data----------------------------------#
    db_password = resolve_db_password(inputs, env_vars)
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

    filenames: dict[str, Any]
    if ctx.merge_bool is False:
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
    final_ra, final_dec = choose_coordinates(
        ctx.inputs["name"],
        cen_ra,
        cen_dec,
        fallback_fits_paths=[
            filenames.get("evt2_repro"),
            filenames.get("exp_corr"),
        ],
    )
    if final_ra is not None and final_dec is not None:
        db_service.add_coord(ctx.inputs["name"], final_ra, final_dec)
    else:
        print(
            "WARNING: unable to determine RA/DEC from centroid, NED/CDS, or FITS header. "
            f"Cluster='{ctx.inputs['name']}'."
        )
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


def _fallback_fits_paths(inputs, cluster_name):
    home_dir = inputs.get("home_dir")
    if not home_dir:
        return []
    cluster_dir = Path(home_dir) / cluster_name
    return [
        str(cluster_dir / "merged_evt.fits"),
        str(cluster_dir / "broad_flux.img"),
    ]


def backfill_missing_coordinates(
    input_path=None, defaults_path=None, sqlite_db_path=None
):
    from db import connect_db
    from db_service import DatabaseService

    if input_path:
        inputs, _merge_bool, env_vars = load_config(input_path)
    else:
        defaults = defaults_path or str(
            Path(__file__).resolve().parent.parent / "inputs" / "template.i"
        )
        inputs, _merge_bool, env_vars = load_config(defaults)

    if sqlite_db_path:
        inputs["db_engine"] = "sqlite"
        inputs["sqlite_db_path"] = sqlite_db_path

    db_password = resolve_db_password(inputs, env_vars)
    mydb, mycursor, db_user, db_host, db_name = connect_db(inputs, db_password)
    db_service = DatabaseService(mydb, mycursor, db_user, db_password, db_host, db_name)

    missing_sql = """
        SELECT Name
        FROM Clusters
        WHERE
            RightAsc IS NULL OR Declination IS NULL OR
            TRIM(RightAsc) = '' OR TRIM(Declination) = '' OR
            LOWER(TRIM(RightAsc)) IN ('none', 'nan', 'null') OR
            LOWER(TRIM(Declination)) IN ('none', 'nan', 'null')
    """

    updated = 0
    unresolved = []
    try:
        mycursor.execute(missing_sql)
        rows = mycursor.fetchall()
        names = [row[0] for row in rows if row and row[0]]
        print(f"Found {len(names)} clusters missing RA/DEC")

        for name in names:
            coords = resolve_coordinates(
                name,
                fallback_fits_paths=_fallback_fits_paths(inputs, name),
            )
            if coords is None:
                unresolved.append(name)
                continue
            db_service.add_coord(name, coords[0], coords[1])
            updated += 1

        print(f"Backfill complete. Updated {updated} clusters.")
        if unresolved:
            print(f"Could not resolve {len(unresolved)} clusters.")
            preview = ", ".join(unresolved[:20])
            if preview:
                print(f"Unresolved (first 20): {preview}")
    finally:
        try:
            mycursor.close()
        except Exception:
            pass
        try:
            mydb.close()
        except Exception:
            pass
    return None


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
    parser.add_argument(
        "--backfill-missing-coords",
        action="store_true",
        help=(
            "Scan database for clusters with missing RA/DEC and backfill using "
            "NED, then CDS, then merged FITS headers."
        ),
    )
    parser.add_argument(
        "--sqlite-db",
        help=(
            "SQLite DB path override. In backfill mode, this forces SQLite "
            "and avoids MySQL."
        ),
    )
    args = parser.parse_args(argv)

    using_backfill = bool(args.backfill_missing_coords)
    using_legacy = bool(args.input_path)
    using_new = bool(args.cluster or args.obsids)
    if using_backfill and using_new:
        parser.error("Backfill mode cannot be combined with --cluster/--obsids.")
    if using_backfill:
        return args
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
    if args.backfill_missing_coords:
        return backfill_missing_coordinates(
            input_path=args.input_path,
            defaults_path=args.defaults,
            sqlite_db_path=args.sqlite_db,
        )
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
