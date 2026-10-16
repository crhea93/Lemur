"""Compute every catalog number and figure quoted in the LEMUR paper.

Reads the local catalog database (``make pull-db``) and writes, under --out:

  stats.json            all numbers, machine readable
  stats_macros.tex      the same numbers as LaTeX macros (\\input in the paper)
  table_deepest.tex     the deepest objects by total clean exposure
  figures/*.pdf         redshift, exposure, ObsIDs-per-object, sky map,
                        X-ray center offsets, AstroCLIP similarity

Rerun it whenever the catalog changes; the paper picks up the new numbers.

The CDA search results live in survey/*.csv (one file per query, with the
CDA "Science Category" column). An object counts as a cluster when any of its
ObsIDs is categorized "CLUSTERS OF GALAXIES", and as a galaxy otherwise.

With --data-dir, exposures describe what is actually in each merged image:
an object's exposure is the EXPOSURE keyword of its broad_flux.img, and its
ObsIDs are the merge_obs inputs recorded in the image HISTORY (or the single
OBS_ID of an unmerged image). Objects without an image are left out, and
stats.json counts the images missing some of their catalog ObsIDs. Without
--data-dir, exposures fall back to the nominal CDA exposure of every catalog
ObsID, which overstates objects whose merge is incomplete.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Pipeline"))
from cluster_paths import data_roots, resolve_cluster_file  # noqa: E402

from Pipeline.pipeline import _coerce_coord_value  # noqa: E402

SURVEY_DIR = ROOT / "survey"
CLUSTER_CATEGORY = "CLUSTERS OF GALAXIES"
# ACCEPT core entropies (Cavagnolo et al. 2009) for the cool-core neighbor test.
ACCEPT_CSV = SURVEY_DIR / "accept" / "accept_k0.csv"
ACCEPT_MATCH_ARCSEC = 60.0
COOL_CORE_K0 = 30.0  # keV cm^2
N_PERMUTATIONS = 5000
# Cool-core fraction falls with redshift and neighbors share redshift, so the
# null shuffles cool-core labels only within ACCEPT redshift quantiles.
N_REDSHIFT_STRATA = 5
N_DEEPEST = 10
# Example objects for the similar-objects figure: a relaxed cool core, the
# Bullet Cluster (major merger) and a merger with a cold front.
NEIGHBOR_QUERIES = ("Abell2029", "1E0657-56", "Abell3667")
NEIGHBOR_FIGURE_K = 5


def load_catalog(db_path):
    con = sqlite3.connect(db_path)
    try:
        clusters = pd.read_sql(
            "SELECT ID, Name, redshift, RightAsc, Declination FROM Clusters", con
        )
        obsids = pd.read_sql("SELECT ClusterNumber, Obsid FROM Obsids", con)
        centers = pd.read_sql(
            "SELECT ClusterName, center_ra, center_dec, method FROM cluster_center", con
        )
        embeddings = pd.read_sql("SELECT ClusterName, model, center_ra, center_dec FROM image_embedding", con)
        similar = pd.read_sql(
            "SELECT ClusterName, NeighborName, rank, similarity FROM similar_clusters",
            con,
        )
    finally:
        con.close()
    return clusters, obsids, centers, embeddings, similar


def load_survey(survey_dir):
    """All CDA search results in survey_dir, one row per ObsID."""
    frames = [pd.read_csv(path) for path in sorted(survey_dir.glob("*.csv"))]
    frames = [
        f
        for f in frames
        if {"Obs ID", "Exposure", "Science Category"} <= set(f.columns)
    ]
    survey = pd.concat(frames, ignore_index=True)
    survey["Obs ID"] = pd.to_numeric(survey["Obs ID"], errors="coerce")
    return (
        survey.dropna(subset=["Obs ID"])
        .astype({"Obs ID": int})
        .drop_duplicates("Obs ID")
    )


def merged_obsids(header, image=None):
    """ObsIDs in an image: merge_obs `infiles` from HISTORY, else OBS_ID.

    Since October 2026 the pipeline gives merge_obs a stack file
    (infiles=@<folder>/merge_inputs.lis, kept next to the image); pass the
    image path so the list can be read from it.
    """
    lines = [str(card) for card in header.get("HISTORY", [])]
    starts = [i for i, line in enumerate(lines) if "infiles=" in line]
    if starts:
        # CIAO wraps long parameters over PARM/CONT cards; rejoin until outroot=.
        blob = ""
        for line in lines[starts[-1] :]:
            blob += re.sub(r"\s*ASC\d+\s*$", "", line).replace("PARM  :", "").replace(
                "CONT  :", ""
            ).strip()
            if "outroot=" in blob:
                break
        blob = blob.split("outroot=")[0]
        if "@" in blob and image is not None:
            stack = Path(image).parent / Path(blob.split("@")[-1].strip(" ,'\"")).name
            if stack.exists():
                blob = "," + ",".join(stack.read_text().split())
        return {int(x) for x in re.findall(r"(?:^|[/,=@])(?:acisf)?0*(\d+)[_/]", blob)}
    obs_id = str(header.get("OBS_ID", "")).strip()
    return {int(obs_id)} if obs_id.isdigit() else set()


def image_contents(clusters, links, data_dir):
    """Per object with an image: exposure (ks) and ObsIDs actually merged."""
    from astropy.io import fits

    catalog = links.groupby("ClusterNumber")["Obsid"].apply(set)
    rows = []
    for object_id, name in zip(clusters["ID"], clusters["Name"]):
        image = resolve_cluster_file(data_dir, name)
        if image is None:
            continue
        try:
            header = fits.getheader(image)
            exposure = float(header["EXPOSURE"]) / 1e3
        except (OSError, KeyError, ValueError):
            continue
        merged = merged_obsids(header, image)
        wanted = catalog.get(object_id, set())
        rows.append(
            {
                "Name": name,
                "exposure_ks": exposure,
                "n_merged": len(merged),
                "n_missing": len(wanted - merged),
                "n_not_in_catalog": len(merged - wanted),
            }
        )
    return pd.DataFrame(rows).set_index("Name")


def nominal_exposures(clusters, links, survey):
    """Per object: summed nominal CDA exposure (ks) of every catalog ObsID."""
    nominal = survey.set_index("Obs ID")["Exposure"]
    rows = links.merge(clusters[["ID", "Name"]], left_on="ClusterNumber", right_on="ID")
    rows["exposure_ks"] = rows["Obsid"].map(nominal)
    complete = rows.groupby("Name")["exposure_ks"].apply(lambda s: s.notna().all())
    per_object = rows.groupby("Name").agg(
        exposure_ks=("exposure_ks", "sum"), n_merged=("Obsid", "nunique")
    )
    return per_object[complete].assign(n_missing=0, n_not_in_catalog=0)


def sky_coords(clusters):
    ra = clusters["RightAsc"].map(lambda v: _coerce_coord_value(v, is_ra=True))
    dec = clusters["Declination"].map(_coerce_coord_value)
    return ra.astype(float), dec.astype(float)


def center_offsets_arcsec(centers, clusters, ra, dec):
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    prior = pd.DataFrame({"ClusterName": clusters["Name"], "ra": ra, "dec": dec})
    merged = centers.merge(prior, on="ClusterName").dropna(
        subset=["ra", "dec", "center_ra", "center_dec"]
    )
    a = SkyCoord(
        merged["center_ra"].values * u.deg, merged["center_dec"].values * u.deg
    )
    b = SkyCoord(merged["ra"].values * u.deg, merged["dec"].values * u.deg)
    return merged.assign(offset_arcsec=a.separation(b).arcsec)


def cool_core_agreement(embeddings, similar, accept):
    """How often neighbors share cool-core status, against shuffled labels.

    Each ACCEPT cluster is matched to the closest embedded object within
    ACCEPT_MATCH_ARCSEC of its X-ray center; keeping one object per ACCEPT
    cluster stops duplicate catalog entries of the same cluster (which are
    each other's neighbors) from inflating the agreement. The null shuffles
    labels within N_REDSHIFT_STRATA redshift quantiles.
    """
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    objects = SkyCoord(
        embeddings["center_ra"].values * u.deg, embeddings["center_dec"].values * u.deg
    )
    catalog = SkyCoord(accept["ra_deg"].values * u.deg, accept["dec_deg"].values * u.deg)
    idx, sep, _ = objects.match_to_catalog_sky(catalog)
    matches = pd.DataFrame(
        {"name": embeddings["ClusterName"].values, "accept": idx, "sep": sep.arcsec}
    )
    matches = matches[matches["sep"] <= ACCEPT_MATCH_ARCSEC].sort_values("sep")
    matches = matches.drop_duplicates("accept")
    k0 = pd.Series(accept["K0"].values[matches["accept"]], index=matches["name"].values)
    strata = pd.qcut(
        pd.Series(accept["z"].values[matches["accept"]], index=k0.index),
        N_REDSHIFT_STRATA,
        labels=False,
    )

    pairs = similar[similar["ClusterName"].isin(k0.index) & similar["NeighborName"].isin(k0.index)]
    if pairs.empty:
        return {}
    cool = k0 < COOL_CORE_K0

    def agreement(labels):
        return float(
            (pairs["ClusterName"].map(labels).values == pairs["NeighborName"].map(labels).values).mean()
        )

    def shuffled(rng):
        labels = cool.copy()
        for stratum in range(N_REDSHIFT_STRATA):
            members = strata.index[strata == stratum]
            labels[members] = rng.permutation(cool[members].values)
        return labels

    observed = agreement(cool)
    rng = np.random.default_rng(0)
    null = np.array([agreement(shuffled(rng)) for _ in range(N_PERMUTATIONS)])
    query_cool = pairs["ClusterName"].map(cool)
    neighbor_cool = pairs["NeighborName"].map(cool)
    return {
        "n_accept_matched": int(len(k0)),
        "n_accept_pairs": int(len(pairs)),
        "accept_cool_core_fraction": float(cool.mean()),
        "cc_agreement": observed,
        "cc_agreement_null_mean": float(null.mean()),
        "cc_agreement_null_std": float(null.std()),
        "cc_agreement_n_null_at_least": int((null >= observed).sum()),
        "cc_neighbor_fraction_given_cc": float(neighbor_cool[query_cool].mean()),
        "cc_neighbor_fraction_given_ncc": float(neighbor_cool[~query_cool].mean()),
    }


def compute_stats(clusters, obsids, centers, embeddings, similar, survey, data_dir):
    stats = {}
    cluster_obsids = set(
        survey.loc[
            survey["Science Category"].str.upper() == CLUSTER_CATEGORY, "Obs ID"
        ].astype(int)
    )

    links = obsids.drop_duplicates(["ClusterNumber", "Obsid"])
    stats["n_duplicate_obsid_links"] = int(len(obsids) - len(links))
    stats["n_objects"] = int(len(clusters))
    stats["n_objects_with_obsids"] = int(links["ClusterNumber"].nunique())
    stats["n_obsids"] = int(links["Obsid"].nunique())
    stats["n_obsids_shared"] = int(
        (links.groupby("Obsid")["ClusterNumber"].nunique() > 1).sum()
    )

    is_cluster = (
        links.assign(c=links["Obsid"].isin(cluster_obsids))
        .groupby("ClusterNumber")["c"]
        .any()
    )
    clusters = clusters.assign(
        is_cluster=clusters["ID"].map(is_cluster).fillna(False).astype(bool)
    )
    stats["n_clusters"] = int(clusters["is_cluster"].sum())
    stats["n_galaxies"] = int((~clusters["is_cluster"]).sum())

    per_object = links.groupby("ClusterNumber")["Obsid"].nunique()
    stats["obsids_per_object_median"] = float(per_object.median())
    stats["obsids_per_object_max"] = int(per_object.max())
    stats["n_objects_multi_obsid"] = int((per_object > 1).sum())

    # z == 0 is how an unresolved redshift is stored; M33's small blueshift is real.
    z = clusters["redshift"].where(clusters["redshift"] != 0)
    stats["n_with_redshift"] = int(z.notna().sum())
    stats["redshift_median"] = float(z.median())
    stats["redshift_max"] = float(z.max())
    stats["n_redshift_above_1"] = int((z > 1).sum())

    contents = (
        image_contents(clusters, links, data_dir)
        if data_dir
        else nominal_exposures(clusters, links, survey)
    )
    stats["exposure_source"] = "merged_image" if data_dir else "cda_nominal"
    stats["n_images_incomplete"] = int((contents["n_missing"] > 0).sum())
    stats["n_obsids_missing_from_images"] = int(contents["n_missing"].sum())
    # Merged ObsIDs that the Obsids table does not list for the object.
    stats["n_images_with_uncataloged_obsids"] = int((contents["n_not_in_catalog"] > 0).sum())
    total = contents["exposure_ks"]
    stats["n_objects_with_exposure"] = int(len(total))
    stats["exposure_total_Ms"] = float(total.sum() / 1e3)
    stats["exposure_per_object_median_ks"] = float(total.median())
    stats["exposure_per_object_max_ks"] = float(total.max())
    stats["n_objects_above_100ks"] = int((total > 100).sum())
    stats["n_objects_above_1Ms"] = int((total > 1000).sum())

    ra, dec = sky_coords(clusters)
    stats["n_with_coordinates"] = int((ra.notna() & dec.notna()).sum())

    stats["n_centers"] = int(len(centers))
    stats["center_methods"] = centers["method"].value_counts().to_dict()
    offsets = center_offsets_arcsec(centers, clusters, ra, dec)
    peak = offsets.loc[
        offsets["method"] == "xray_bandpass_peak", "offset_arcsec"
    ].values
    stats["center_offset_median_arcsec"] = float(np.median(peak)) if len(peak) else None
    stats["center_offset_p75_arcsec"] = float(np.percentile(peak, 75)) if len(peak) else None
    stats["n_center_offset_within_30arcsec"] = int((peak <= 30).sum())
    stats["n_center_offset_above_2arcmin"] = int((peak > 120).sum())

    stats["n_embeddings"] = int(len(embeddings))
    stats["embedding_models"] = embeddings["model"].value_counts().to_dict()
    top1 = similar[
        similar["rank"] == similar.groupby("ClusterName")["rank"].transform("min")
    ]
    stats["neighbors_per_object"] = (
        int(similar.groupby("ClusterName").size().median()) if len(similar) else 0
    )
    stats["top1_similarity_median"] = (
        float(top1["similarity"].median()) if len(top1) else None
    )
    stats["similarity_median"] = (
        float(similar["similarity"].median()) if len(similar) else None
    )

    # Do neighbors share redshift more than random pairs of embedded objects?
    log_z = np.log10(z.where(z > 0)).set_axis(clusters["Name"])
    pairs = similar.assign(
        a=similar["ClusterName"].map(log_z), b=similar["NeighborName"].map(log_z)
    ).dropna(subset=["a", "b"])
    pool = log_z.reindex(embeddings["ClusterName"]).dropna().values
    rng = np.random.default_rng(0)
    embedded_is_cluster = (
        clusters.set_index("Name")["is_cluster"].reindex(embeddings["ClusterName"])
    )
    stats["n_embedded_clusters"] = int(embedded_is_cluster.fillna(False).sum())
    stats["neighbor_dlogz_median"] = (
        float(np.median(np.abs(pairs["a"] - pairs["b"]))) if len(pairs) else None
    )
    stats["random_dlogz_median"] = (
        float(np.median(np.abs(rng.choice(pool, 100_000) - rng.choice(pool, 100_000))))
        if len(pool) > 1
        else None
    )

    if ACCEPT_CSV.exists():
        stats.update(
            cool_core_agreement(embeddings, similar, pd.read_csv(ACCEPT_CSV, comment="#"))
        )

    frames = {
        "clusters": clusters,
        "z": z,
        "exposure": total,
        "n_merged": contents["n_merged"],
        "per_object": per_object,
        "ra": ra,
        "dec": dec,
        "offsets": peak,
        "top1": top1,
        "similar": similar,
    }
    return stats, frames


def fmt(value, digits=0):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "--"
    if digits == 0:
        return f"{int(round(value)):,}".replace(",", "{,}")
    return f"{value:.{digits}f}"


def write_macros(stats, path):
    macros = {
        "nObjects": fmt(stats["n_objects"]),
        "nClusters": fmt(stats["n_clusters"]),
        "nGalaxies": fmt(stats["n_galaxies"]),
        "nObsIDs": fmt(stats["n_obsids"]),
        "nMultiObsID": fmt(stats["n_objects_multi_obsid"]),
        "maxObsIDsPerObject": fmt(stats["obsids_per_object_max"]),
        "nWithRedshift": fmt(stats["n_with_redshift"]),
        "medianRedshift": fmt(stats["redshift_median"], 3),
        "maxRedshift": fmt(stats["redshift_max"], 2),
        "totalExposureMs": fmt(stats["exposure_total_Ms"], 1),
        "medianExposureKs": fmt(stats["exposure_per_object_median_ks"], 1),
        "maxExposureMs": fmt(stats["exposure_per_object_max_ks"] / 1e3, 2),
        "nAboveHundredKs": fmt(stats["n_objects_above_100ks"]),
        "nCenters": fmt(stats["n_centers"]),
        "nCentersPeak": fmt(stats["center_methods"].get("xray_bandpass_peak", 0)),
        "nCentersFallback": fmt(
            stats["center_methods"].get("placeholder_existing_centroid", 0)
        ),
        "medianCenterOffset": fmt(stats["center_offset_median_arcsec"], 0),
        "upperQuartileCenterOffset": fmt(stats["center_offset_p75_arcsec"], 0),
        "nCenterWithinThirtyArcsec": fmt(stats["n_center_offset_within_30arcsec"]),
        "nCenterBeyondTwoArcmin": fmt(stats["n_center_offset_above_2arcmin"]),
        "nEmbeddings": fmt(stats["n_embeddings"]),
        "nNeighbors": fmt(stats["neighbors_per_object"]),
        "medianTopSimilarity": fmt(stats["top1_similarity_median"], 3),
        "medianSimilarity": fmt(stats["similarity_median"], 3),
        "nEmbeddedClusters": fmt(stats["n_embedded_clusters"]),
        "neighborDlogZ": fmt(stats["neighbor_dlogz_median"], 2),
        "randomDlogZ": fmt(stats["random_dlogz_median"], 2),
        "nAcceptMatched": fmt(stats.get("n_accept_matched")),
        "nAcceptPairs": fmt(stats.get("n_accept_pairs")),
        "acceptCoolCorePercent": fmt(100 * stats.get("accept_cool_core_fraction", np.nan)),
        "ccAgreementPercent": fmt(100 * stats.get("cc_agreement", np.nan)),
        "ccNullPercent": fmt(100 * stats.get("cc_agreement_null_mean", np.nan)),
        "ccSignificance": fmt(
            (stats.get("cc_agreement", np.nan) - stats.get("cc_agreement_null_mean", np.nan))
            / stats.get("cc_agreement_null_std", np.nan),
            0,
        ),
        "ccGivenCCPercent": fmt(100 * stats.get("cc_neighbor_fraction_given_cc", np.nan)),
        "ccGivenNCCPercent": fmt(100 * stats.get("cc_neighbor_fraction_given_ncc", np.nan)),
        "nPermutations": fmt(N_PERMUTATIONS),
        "nRedshiftStrata": fmt(N_REDSHIFT_STRATA),
    }
    lines = ["% Generated by scripts/paper_stats.py -- do not edit by hand."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    path.write_text("\n".join(lines) + "\n")


def redshift_cell(z):
    """Table cell for a redshift: N/A when unknown, a math minus for blueshifts."""
    if not z:
        return "N/A"
    return f"${fmt(z, 4)}$" if z < 0 else fmt(z, 4)


def write_deepest_table(frames, path):
    clusters = frames["clusters"].set_index("Name")
    deepest = frames["exposure"].sort_values(ascending=False).head(N_DEEPEST)
    n_merged = frames["n_merged"]
    rows, n_clusters = [], 0
    width = max(len(name) for name in deepest.index)
    for name, ks in deepest.items():
        c = clusters.loc[name]
        n_clusters += bool(c["is_cluster"])
        z = c["redshift"]
        rows.append(
            f"{name.ljust(width)} & {redshift_cell(z)} & {n_merged[name]} & "
            f"{ks / 1e3:.2f} \\\\"
        )
    count = {10: "ten"}.get(N_DEEPEST, str(N_DEEPEST))
    n_galaxies = len(rows) - n_clusters
    if n_galaxies == 0:
        what = ", all of which are galaxy clusters"
    elif n_clusters == 0:
        what = ", all of which are galaxies"
    else:
        what = f": {n_clusters} galaxy clusters and {n_galaxies} galaxies"
    path.write_text(
        "% Generated by scripts/paper_stats.py -- do not edit by hand.\n"
        "\\begin{table}[t]\n"
        "\\centering\n"
        f"\\caption{{The {count} deepest objects in the LEMUR catalog{what}.}}\n"
        "\\label{tab:deepest}\n"
        "\\begin{tabular}{lccc}\n"
        "\\hline\n"
        "Name & $z$ & $N_{\\rm ObsID}$ & Exposure (Ms) \\\\\n"
        "\\hline\n" + "\n".join(rows) + "\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def make_figures(frames, stats, out_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"font.size": 9, "figure.figsize": (3.4, 2.6), "savefig.bbox": "tight"}
    )
    is_cluster = frames["clusters"]["is_cluster"].values
    colors = {"Clusters": "#1f77b4", "Galaxies": "#d62728"}

    def save(fig, name):
        fig.savefig(out_dir / f"{name}.pdf")
        plt.close(fig)

    def draw_redshift(ax):
        z = frames["z"]
        bins = np.logspace(-4, np.log10(z.max()), 31)
        for label, mask in (("Clusters", is_cluster), ("Galaxies", ~is_cluster)):
            ax.hist(
                z[mask].dropna(),
                bins=bins,
                histtype="step",
                lw=1.2,
                color=colors[label],
                label=label,
            )
        ax.set(xscale="log", xlabel="Redshift", ylabel="Objects")

    def draw_sky(ax):
        ra, dec = frames["ra"], frames["dec"]
        wrap = np.radians(-(((ra + 180) % 360) - 180))  # RA increasing to the left
        for label, mask in (("Clusters", is_cluster), ("Galaxies", ~is_cluster)):
            ax.scatter(
                wrap[mask],
                np.radians(dec[mask]),
                s=3,
                color=colors[label],
                label=label,
                alpha=0.7,
                linewidths=0,
            )
        ax.set_xticklabels(
            [f"{d}°" for d in (150, 120, 90, 60, 30, 0, 330, 300, 270, 240, 210)]
        )
        ax.grid(alpha=0.3)

    fig, ax = plt.subplots()
    draw_redshift(ax)
    ax.legend(frameon=False)
    save(fig, "redshift_hist")

    fig = plt.figure(figsize=(7, 3.6))
    ax = fig.add_subplot(projection="aitoff")
    draw_sky(ax)
    ax.legend(frameon=False, loc="lower right", markerscale=3)
    save(fig, "sky_map")

    # Paper figure: sky map (left, two thirds) and redshift distribution (right).
    fig = plt.figure(figsize=(7.1, 2.5))
    grid = fig.add_gridspec(1, 2, width_ratios=[2.2, 1], wspace=0.28)
    sky = fig.add_subplot(grid[0, 0], projection="aitoff")
    draw_sky(sky)
    sky.tick_params(labelsize=7)
    sky.set_title("(a)", loc="left", fontsize=9)
    hist = fig.add_subplot(grid[0, 1])
    draw_redshift(hist)
    hist.set_title("(b)", loc="left", fontsize=9)
    hist.legend(frameon=False, fontsize=8, loc="upper left")
    save(fig, "catalog_overview")

    names = frames["clusters"].set_index("Name")["is_cluster"]
    exposure = frames["exposure"]
    fig, ax = plt.subplots()
    bins = np.logspace(np.log10(max(exposure.min(), 0.1)), np.log10(exposure.max()), 31)
    for label, want in (("Clusters", True), ("Galaxies", False)):
        ax.hist(
            exposure[names.loc[exposure.index].values == want],
            bins=bins,
            histtype="step",
            lw=1.2,
            color=colors[label],
            label=label,
        )
    ax.set(xscale="log", xlabel="Total clean exposure (ks)", ylabel="Objects")
    ax.legend(frameon=False)
    save(fig, "exposure_hist")

    per_object = frames["per_object"]
    fig, ax = plt.subplots()
    ax.hist(per_object, bins=np.arange(1, per_object.max() + 2) - 0.5, color="0.4")
    ax.set(yscale="log", xlabel="ObsIDs per object", ylabel="Objects")
    save(fig, "obsids_per_object")

    offsets = frames["offsets"]
    if len(offsets):
        fig, ax = plt.subplots()
        ax.hist(
            np.clip(offsets, 0.1, None),
            bins=np.logspace(-1, np.log10(max(offsets.max(), 10)), 31),
            color="0.4",
        )
        ax.set(
            xscale="log",
            xlabel="X-ray peak $-$ target position (arcsec)",
            ylabel="Objects",
        )
        save(fig, "center_offsets")

    similar = frames["similar"]
    if len(similar):
        fig, ax = plt.subplots()
        bins = np.linspace(similar["similarity"].min(), 1, 31)
        ax.hist(
            similar["similarity"],
            bins=bins,
            histtype="step",
            lw=1.2,
            color="0.4",
            label="All neighbors",
        )
        ax.hist(
            frames["top1"]["similarity"],
            bins=bins,
            histtype="step",
            lw=1.2,
            color="#1f77b4",
            label="Nearest neighbor",
        )
        ax.set(xlabel="Cosine similarity", ylabel="Pairs")
        ax.legend(frameon=False, loc="upper left")
        save(fig, "similarity_hist")


def make_neighbor_figure(db_path, data_dir, out_path, queries, k=NEIGHBOR_FIGURE_K):
    """Grid of the encoder's input images: each query and its top-k neighbors."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from embeddings import common_grid_size, make_cutout, prepare_image

    con = sqlite3.connect(db_path)
    try:
        embedded = pd.read_sql(
            "SELECT ClusterName, center_ra, center_dec, cutout_size FROM image_embedding",
            con,
        ).set_index("ClusterName")
        similar = pd.read_sql(
            "SELECT ClusterName, NeighborName, similarity FROM similar_clusters ORDER BY rank",
            con,
        )
    finally:
        con.close()
    queries = [q for q in queries if q in embedded.index]
    if not queries:
        print("No neighbor-figure queries have embeddings; skipping.")
        return

    def encoder_input(name):
        row = embedded.loc[name]
        size = int(row["cutout_size"])
        path = resolve_cluster_file(data_dir, name)
        cutout = make_cutout(str(path), row["center_ra"], row["center_dec"], size)
        return prepare_image(cutout, common_grid_size(size))

    fig, axes = plt.subplots(
        len(queries), k + 1, figsize=(7.1, 1.5 * len(queries) + 0.2), squeeze=False
    )
    for row_axes, query in zip(axes, queries):
        neighbors = similar[similar["ClusterName"] == query].head(k)
        panels = [(query, None)] + list(zip(neighbors["NeighborName"], neighbors["similarity"]))
        for ax, (name, sim) in zip(row_axes, panels):
            ax.imshow(encoder_input(name), cmap="magma", origin="lower", vmin=0, vmax=1)
            label = name if sim is None else f"{name}\n{sim:.3f}"
            ax.set_title(label, fontsize=6.5, fontweight="bold" if sim is None else "normal")
            ax.set_xticks([])
            ax.set_yticks([])
        for spine in row_axes[0].spines.values():
            spine.set_edgecolor("#1f77b4")
            spine.set_linewidth(2)
    fig.tight_layout(pad=0.3, h_pad=1.2, w_pad=0.3)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("LEMUR_DB_PATH", ROOT / "api" / "data" / "lemur.db"),
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("LEMUR_CHANDRA_DIR", ""),
        help="Data folder(s) for clean exposures from event files (':'-separated)",
    )
    parser.add_argument("--out", default=ROOT / "paper", type=Path)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()

    data_dir = (
        args.data_dir if any(p.is_dir() for p in data_roots(args.data_dir)) else ""
    )
    if args.data_dir and not data_dir:
        print(f"Data folder not found ({args.data_dir}); using nominal CDA exposures.")

    survey = load_survey(SURVEY_DIR)
    stats, frames = compute_stats(*load_catalog(args.db), survey, data_dir)

    (args.out / "figures").mkdir(parents=True, exist_ok=True)
    (args.out / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    write_macros(stats, args.out / "stats_macros.tex")
    write_deepest_table(frames, args.out / "table_deepest.tex")
    if not args.no_figures:
        make_figures(frames, stats, args.out / "figures")
        if data_dir:
            make_neighbor_figure(
                args.db, data_dir, args.out / "figures" / "neighbors.pdf", NEIGHBOR_QUERIES
            )

    print(json.dumps(stats, indent=2))
    print(
        f"Wrote {args.out}/stats.json, stats_macros.tex, table_deepest.tex"
        + ("" if args.no_figures else ", figures/*.pdf")
    )


if __name__ == "__main__":
    main()
