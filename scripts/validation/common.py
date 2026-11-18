"""Shared helpers for the image validation (paper Section 3.2).

The CSC queries go to the Chandra Source Catalog 2.1 TAP service; it does not
support ADQL geometry, so cones are queried as RA/Dec boxes.
"""

import gzip
import io
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Pipeline"))
from cluster_paths import data_roots, resolve_cluster_file  # noqa: E402,F401

from Pipeline.pipeline import _coerce_coord_value  # noqa: E402

DATA_DIR = os.environ.get("LEMUR_CHANDRA_DIR", "")
DB_PATH = Path(os.environ.get("LEMUR_DB_PATH", ROOT / "api" / "data" / "lemur.db"))
# CDA observation catalog (ACIS, all categories) saved from the ChaSeR search
# on 2026-11-02; used for observation start dates.
OCAT = Path(os.environ.get("LEMUR_OCAT", ROOT / "api" / "data" / "cda_acis_ocat_2026-11-02.tsv"))
TAP = "https://cda.cfa.harvard.edu/csc21tap/sync"
CSC_FLAGS = ("extent_flag", "var_flag", "pileup_flag", "conf_flag", "sat_src_flag", "streak_src_flag")


def csc_sources(ra, dec, radius_arcmin, columns):
    """CSC 2.1 master sources in a box around (ra, dec), or None on failure."""
    from astropy.io.votable import parse

    r = radius_arcmin / 60.0
    dra = r / max(np.cos(np.radians(dec)), 1e-3)
    query = (
        f"SELECT {', '.join('m.' + c for c in columns)} FROM csc21.master_source m "
        f"WHERE m.dec BETWEEN {dec - r} AND {dec + r} AND m.ra BETWEEN {ra - dra} AND {ra + dra}"
    )
    data = urllib.parse.urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "QUERY": query}).encode()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(TAP, data=data), timeout=120) as resp:
                return parse(io.BytesIO(resp.read())).get_first_table().to_table().to_pandas()
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def load_image(path):
    """(data, header) of a FITS image, reading path or path.gz."""
    from astropy.io import fits

    path = Path(path)
    if path.exists():
        with fits.open(path) as h:
            return h[0].data.astype(np.float64), h[0].header
    with gzip.open(Path(str(path) + ".gz")) as f, fits.open(io.BytesIO(f.read())) as h:
        return h[0].data.astype(np.float64), h[0].header


def object_folder(name):
    image = resolve_cluster_file(DATA_DIR, name)
    if image is None:
        raise FileNotFoundError(f"no image for {name} in {DATA_DIR}")
    return image.parent


def eligible_objects(max_obsids):
    """Objects with at most max_obsids ObsIDs, all started before 2022 (so CSC
    2.1 contains the same observations), with target positions in degrees."""
    ocat = pd.read_csv(OCAT, sep="\t", comment="#", low_memory=False, encoding="latin-1")
    ocat["Obs ID"] = pd.to_numeric(ocat["Obs ID"], errors="coerce")
    start = ocat.dropna(subset=["Obs ID"]).astype({"Obs ID": int}).set_index("Obs ID")["Start Date"]
    links = pd.read_sql(
        "SELECT c.Name, c.RightAsc, c.Declination, o.Obsid FROM Clusters c "
        "JOIN Obsids o ON o.ClusterNumber = c.ID",
        sqlite3.connect(DB_PATH),
    )
    links["start"] = links.Obsid.map(start).astype(str)
    g = links.groupby("Name").agg(
        ra=("RightAsc", "first"), dec=("Declination", "first"),
        n=("Obsid", "nunique"), last=("start", "max"),
    )
    g = g[(g.n <= max_obsids) & (g["last"] < "2022")]
    g["ra"] = g.ra.map(lambda v: _coerce_coord_value(v, is_ra=True))
    g["dec"] = g.dec.map(_coerce_coord_value)
    return g.dropna(subset=["ra", "dec"])


def mean_start_year():
    """{object name: mean start year of its ObsIDs}."""
    ocat = pd.read_csv(OCAT, sep="\t", comment="#", low_memory=False, encoding="latin-1")
    ocat["Obs ID"] = pd.to_numeric(ocat["Obs ID"], errors="coerce")
    start = ocat.dropna(subset=["Obs ID"]).astype({"Obs ID": int}).set_index("Obs ID")["Start Date"]
    links = pd.read_sql(
        "SELECT c.Name, o.Obsid FROM Clusters c JOIN Obsids o ON o.ClusterNumber = c.ID",
        sqlite3.connect(DB_PATH),
    )
    links["year"] = pd.to_datetime(links.Obsid.map(start), errors="coerce").dt.year
    return links.groupby("Name").year.mean()
