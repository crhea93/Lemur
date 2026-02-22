import json
import re
from pathlib import Path

import pandas as pd

try:
    import pickle
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Failed to import pickle: {exc}")

try:
    from astroquery.ned import Ned
    from astroquery.simbad import Simbad
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "astroquery is required. Install with: pip install astroquery\n"
        f"Import error: {exc}"
    )


PICKLE_PATH = Path("/home/carterrhea/Downloads/clusters_grouped.pkl")
CSV_PATH = Path("/home/carterrhea/Downloads/galaxyClusters.csv")
TEMPLATE_PATH = Path("/home/carterrhea/Documents/Lemur/inputs/Abell133.i")
OUT_DIR = Path("/home/carterrhea/Documents/Lemur/inputs/generated")
CACHE_PATH = Path("/home/carterrhea/Documents/Lemur/inputs/redshift_cache.json")


def load_template_values(template_path):
    values = {}
    for line in template_path.read_text().splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            values[key.strip().lower()] = val.strip()
    return values


def sanitize_name(name):
    return re.sub(r"[^A-Za-z0-9+\\-_]", "", name.strip().replace(" ", ""))


def load_cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def get_redshift_from_ned(name):
    try:
        result = Ned.query_object(name)
        if len(result) == 0:
            return None
        z = result["Redshift"][0]
        if z is None or str(z).strip() == "":
            return None
        return float(z)
    except Exception:
        return None


def get_redshift_from_simbad(name):
    try:
        custom = Simbad()
        custom.add_votable_fields("z_value")
        result = custom.query_object(name)
        if result is None or len(result) == 0:
            return None
        z = result["Z_VALUE"][0]
        if z is None or str(z).strip() == "":
            return None
        return float(z)
    except Exception:
        return None


def resolve_redshift(name, cache):
    if name in cache and cache[name] is not None:
        return cache[name]

    z = get_redshift_from_ned(name)
    if z is None:
        z = get_redshift_from_simbad(name)

    cache[name] = z
    return z


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    template_vals = load_template_values(TEMPLATE_PATH)
    home_dir = template_vals.get("home_dir")
    web_dir = template_vals.get("web_dir")

    with PICKLE_PATH.open("rb") as f:
        clusters = pickle.load(f)

    df = pd.read_csv(CSV_PATH)
    df["Obs ID"] = df["Obs ID"].astype(int)
    obsid_to_name = dict(zip(df["Obs ID"], df["Target Name"]))

    cache = load_cache()

    missing_redshift = []
    for i, cl in enumerate(clusters, start=1):
        obsids = sorted(set(int(x) for x in cl["obsids"]))
        raw_name = obsid_to_name.get(obsids[0], f"Cluster_{i:04d}")
        name = sanitize_name(raw_name) or f"Cluster_{i:04d}"

        z = resolve_redshift(raw_name, cache)
        if z is None:
            missing_redshift.append(raw_name)
            z = 0.0

        merge = "True" if len(obsids) > 1 else "False"
        out_path = OUT_DIR / f"{name}.i"
        out_path.write_text(
            "\n".join(
                [
                    "#INPUT FILE: All lines starting with # will not be read",
                    "#-----Directory Info-----#",
                    f"home_dir = {home_dir}",
                    f"web_dir = {web_dir}",
                    f"dir_list = {','.join(str(o) for o in obsids)}",
                    f"name = {name}",
                    "#-----Parameter info-----#",
                    f"redshift = {z}",
                    "#-----Additional Info----#",
                    f"merge = {merge}",
                    "cleaning = false",
                    "surface_brightness_calc = false",
                    "",
                    "# API update options",
                    "update_api = true",
                    "sql_dump_path = /home/carterrhea/Documents/Lemur/lemur.sql",
                    "sqlite_db_path = /home/carterrhea/Documents/Lemur/api/data/lemur.db",
                    "",
                    "# Optional API restart (uvicorn)",
                    "api_restart = false",
                    "api_health_url = http://localhost:8000/api/health",
                    'api_restart_cmd = pkill -f "uvicorn api.app:app" || true; uvicorn api.app:app --reload --host 0.0.0.0 --port 8000 &',
                ]
            )
            + "\n"
        )

    save_cache(cache)
    print(f"Wrote {len(clusters)} input files to {OUT_DIR}")
    if missing_redshift:
        print("Missing redshifts (set to 0.0). Example:")
        print("  " + ", ".join(missing_redshift[:10]))


if __name__ == "__main__":
    main()
