"""Catalog tables of a LEMUR data release, for the Zenodo snapshot.

Writes to OUT_DIR (default paper/release_dr1):
  lemur_dr1_objects.csv     one row per object: class, target position,
                            X-ray center, redshift, ObsIDs, clean exposure, URL
  lemur_dr1_obsids.csv      object -> ObsID, one row per pair
  lemur_dr1_neighbors.csv   the 10 most similar objects of each object
  lemur_dr1_embeddings.npz  AstroCLIP embeddings (names, float32 [N, 1024])
  README.md                 description of the files and columns

The images themselves are served by the web archive. The clean exposure of
each object is read from its merged image (as in paper_stats.py), so the data
folder must be mounted.

    python scripts/make_data_release.py --db api/data/lemur.db \
        --data-dir "$LEMUR_CHANDRA_DIR" --out paper/release_dr1
"""

import argparse
import importlib.util
import sqlite3
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "DR1"
SITE = "https://lemur-archive.lemur-xray.workers.dev"
EMBEDDING_MODEL = "astroclip-chandra-broad"


def paper_stats():
    spec = importlib.util.spec_from_file_location("paper_stats", ROOT / "scripts" / "paper_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(db, data_dir, out):
    ps = paper_stats()
    clusters, obsids, centers, embeddings, similar = ps.load_catalog(db)
    stats, frames = ps.compute_stats(
        clusters, obsids, centers, embeddings, similar, ps.load_survey(ps.SURVEY_DIR), data_dir
    )
    objects = frames["clusters"].copy()
    objects["ra_target_deg"], objects["dec_target_deg"] = ps.sky_coords(objects)
    links = obsids.merge(objects[["ID", "Name"]], left_on="ClusterNumber", right_on="ID")
    by_object = links.groupby("Name")["Obsid"].apply(lambda s: sorted(set(int(o) for o in s)))
    center = centers.set_index("ClusterName")
    z = pd.to_numeric(objects["redshift"], errors="coerce")
    table = pd.DataFrame(
        {
            "name": objects["Name"],
            "class": np.where(objects["is_cluster"], "cluster", "galaxy"),
            "ra_target_deg": objects["ra_target_deg"].round(6),
            "dec_target_deg": objects["dec_target_deg"].round(6),
            "ra_xray_deg": objects["Name"].map(center["center_ra"]).round(6),
            "dec_xray_deg": objects["Name"].map(center["center_dec"]).round(6),
            "center_method": objects["Name"].map(center["method"]),
            "redshift": z.where(z != 0),
            "n_obsids": objects["Name"].map(by_object.map(len)).fillna(0).astype(int),
            "obsids": objects["Name"].map(by_object.map(lambda o: ";".join(map(str, o)))),
            "exposure_ks": objects["Name"].map(frames["exposure"]).round(2),
            "url": objects["Name"].map(
                lambda n: f"{SITE}/cluster?name={urllib.parse.quote(n)}"
            ),
        }
    ).sort_values("name", key=lambda s: s.str.lower())
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "lemur_dr1_objects.csv", index=False)

    pairs = (
        links[["Name", "Obsid"]]
        .drop_duplicates()
        .rename(columns={"Name": "name", "Obsid": "obsid"})
        .sort_values(["name", "obsid"])
    )
    pairs.to_csv(out / "lemur_dr1_obsids.csv", index=False)

    neighbors = similar.rename(
        columns={"ClusterName": "name", "NeighborName": "neighbor"}
    )[["name", "rank", "neighbor", "similarity"]].sort_values(["name", "rank"])
    neighbors["similarity"] = neighbors["similarity"].round(5)
    neighbors.to_csv(out / "lemur_dr1_neighbors.csv", index=False)

    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT ClusterName, dim, embedding FROM image_embedding WHERE model = ? ORDER BY ClusterName",
        (EMBEDDING_MODEL,),
    ).fetchall()
    con.close()
    names = np.array([r[0] for r in rows])
    vectors = np.stack([np.frombuffer(r[2], dtype=np.float32, count=r[1]) for r in rows])
    np.savez_compressed(
        out / "lemur_dr1_embeddings.npz", names=names, embeddings=vectors, model=EMBEDDING_MODEL
    )

    (out / "README.md").write_text(readme(table, pairs, neighbors, vectors, stats))
    return table


def readme(table, pairs, neighbors, vectors, stats):
    n_cl = int((table["class"] == "cluster").sum())
    return f"""# LEMUR {RELEASE}: catalog tables

LEMUR is a searchable archive of uniformly reduced, merged *Chandra* ACIS
images of galaxies and galaxy clusters. This record holds the catalog tables
of data release {RELEASE} ({date.today().isoformat()}): {len(table):,} objects
({n_cl:,} clusters and {len(table) - n_cl:,} galaxies) built from
{len(pairs.obsid.unique()):,} ObsIDs and {stats['exposure_total_Ms']:.1f} Ms of clean exposure.
The images (background-subtracted, exposure-corrected flux, counts, background
and exposure maps in 0.5-7, 0.5-2 and 2-7 keV) are served by the web archive,
{SITE}/, and the `url` column links each object's page and downloads. The
code that builds the catalog is at https://github.com/crhea93/Lemur.

The archive selection is every ACIS imaging observation in the Chandra Data
Archive under the "normal galaxies" and "clusters of galaxies" science
categories (search of 2026-11-02), excluding calibration and offset-field
pointings; observations were reduced with CIAO 4.18.0, CALDB 4.12.4 and the
ACIS blank-sky background files 4.9.7. See the LEMUR paper for details.

## lemur_dr1_objects.csv

| column | description |
|---|---|
| name | object name used by the archive |
| class | `cluster` if any ObsID is in the CDA category "clusters of galaxies", else `galaxy` |
| ra_target_deg, dec_target_deg | target position (RA_TARG/DEC_TARG of the merged image), degrees ICRS |
| ra_xray_deg, dec_xray_deg | X-ray center: peak of the diffuse 0.5-7 keV emission near the target, degrees |
| center_method | `xray_bandpass_peak` (significant peak found) or `target_position` (none found; the X-ray center is the target position) |
| redshift | redshift from NED or SIMBAD; empty if unknown |
| n_obsids, obsids | number and list (`;`-separated) of the ObsIDs merged into the image |
| exposure_ks | total clean exposure of the merged image, ks |
| url | the object's page in the web archive |

## lemur_dr1_obsids.csv

`name`, `obsid`: one row per object and merged ObsID.

## lemur_dr1_neighbors.csv

`name`, `rank` (1 = most similar), `neighbor`, `similarity` (cosine similarity
of AstroCLIP embeddings). {len(neighbors):,} rows, {neighbors['rank'].max()} neighbors per object.
Only the ranking is meaningful; the absolute similarities are compressed
because the X-ray images are far outside AstroCLIP's training data.

## lemur_dr1_embeddings.npz

`names` ({vectors.shape[0]:,}), `embeddings` (float32, {vectors.shape[0]:,} x {vectors.shape[1]},
unit length) and `model`: the AstroCLIP image-encoder embeddings of
4.2' x 4.2' cutouts of the 0.5-7 keV image centered on the X-ray center.

    import numpy as np
    d = np.load("lemur_dr1_embeddings.npz")
    names, emb = d["names"], d["embeddings"]

## Caveats

The flux images use single-energy exposure maps: point-source photon fluxes
agree with the Chandra Source Catalog to 3% in 0.5-7 keV and 4% in 2-7 keV,
but are about 20% low in 0.5-2 keV. About 6% of objects have chips without a
blank-sky background, which are exposure corrected but not background
subtracted.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=ROOT / "api" / "data" / "lemur.db")
    parser.add_argument("--data-dir", required=True, help="Data folder(s) with the merged images")
    parser.add_argument("--out", default=ROOT / "paper" / "release_dr1", type=Path)
    args = parser.parse_args()
    table = build(args.db, args.data_dir, args.out)
    print(f"Wrote {len(table)} objects to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
