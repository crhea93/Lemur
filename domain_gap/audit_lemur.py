"""Phase 1 data audit of the LEMUR images for the simulation-to-observation study.

For every catalog object, records what a common preprocessing pipeline needs to
know: image size, pixel scale and units, whether the image is background
subtracted, clean exposure, instrument configuration, redshift, X-ray center,
the angular size of fixed physical fields of view (250 and 500 kpc boxes,
Planck 2018 cosmology), and how much of each field -- and of LEMUR's fixed
4.2' AstroCLIP cutout -- is covered by exposed pixels. Images are only read
(memory-mapped), never modified.

    python -m domain_gap.audit_lemur --out outputs/audit
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/home/crhea/Projects/Lemur/api/data/lemur.db")
DEFAULT_DATA = Path("/run/media/crhea/ef10789c-0ada-41e4-8d3f-8f17dbcc0558")
SURVEY_CSV = ROOT / "survey" / "galaxyClusters.csv"
CLUSTER_CATEGORY = "CLUSTERS OF GALAXIES"
ACIS_PIXEL_ARCSEC = 0.492
FIELDS_KPC = (250, 500)  # side of the square physical field of view
ASTROCLIP_CUTOUT_PIX = 512  # LEMUR's current fixed-angle cutout: 4.2'
SAMPLES = 400  # exposure-map samples per side when measuring coverage
GOOD_EXPOSURE_FRACTION = 0.1  # "well exposed": > 10% of the 90th percentile


def load_catalog(db_path):
    con = sqlite3.connect(db_path)
    try:
        objects = pd.read_sql("SELECT ID, Name, redshift FROM Clusters", con)
        links = pd.read_sql(
            "SELECT ClusterNumber, Obsid FROM Obsids", con
        ).drop_duplicates()
        centers = pd.read_sql(
            "SELECT ClusterName AS Name, center_ra, center_dec, method FROM cluster_center",
            con,
        )
    finally:
        con.close()
    survey = pd.read_csv(SURVEY_CSV)
    survey["Obs ID"] = pd.to_numeric(survey["Obs ID"], errors="coerce")
    survey = (
        survey.dropna(subset=["Obs ID"])
        .astype({"Obs ID": int})
        .drop_duplicates("Obs ID")
    )
    cluster_obs = set(
        survey.loc[survey["Science Category"].str.upper() == CLUSTER_CATEGORY, "Obs ID"]
    )
    info = survey.set_index("Obs ID")
    rows = []
    for object_id, group in links.groupby("ClusterNumber"):
        obs = group["Obsid"].astype(int).tolist()
        known = [o for o in obs if o in info.index]
        instruments = (
            info.loc[known, "Instrument"].str.upper() if known else pd.Series(dtype=str)
        )
        dates = (
            pd.to_datetime(info.loc[known, "Start Date"], errors="coerce")
            if known
            else pd.Series(dtype="datetime64[ns]")
        )
        rows.append(
            {
                "ID": object_id,
                "n_obsids": len(obs),
                "is_cluster": any(o in cluster_obs for o in obs),
                "n_acis_i": int((instruments == "ACIS-I").sum()),
                "n_acis_s": int((instruments == "ACIS-S").sum()),
                "first_obs": dates.min().date().isoformat()
                if len(dates.dropna())
                else None,
                "last_obs": dates.max().date().isoformat()
                if len(dates.dropna())
                else None,
            }
        )
    objects = objects.merge(pd.DataFrame(rows), on="ID", how="left").merge(
        centers, on="Name", how="left"
    )
    objects["is_cluster"] = objects["is_cluster"].fillna(False).astype(bool)
    return objects


def resolve_folder(data_dir, name):
    sys.path.insert(0, str(ROOT / "Pipeline"))
    from cluster_paths import resolve_cluster_file

    image = resolve_cluster_file(str(data_dir), name)
    return None if image is None else image.parent


def box_coverage(exposure, cx, cy, half, p90):
    """Fractions of a square box (half-side ``half`` pixels) with any / good exposure.

    Pixels outside the image count as unexposed. The box is sampled on a
    SAMPLES x SAMPLES grid so very large boxes stay cheap to evaluate.
    """
    ny, nx = exposure.shape
    xs = np.linspace(cx - half, cx + half, SAMPLES)
    ys = np.linspace(cy - half, cy + half, SAMPLES)
    ix = np.round(xs).astype(int)
    iy = np.round(ys).astype(int)
    inside_x = (ix >= 0) & (ix < nx)
    inside_y = (iy >= 0) & (iy < ny)
    if not inside_x.any() or not inside_y.any():
        return 0.0, 0.0
    sub = np.asarray(exposure[np.ix_(iy[inside_y], ix[inside_x])], dtype=np.float64)
    total = SAMPLES * SAMPLES
    return float((sub > 0).sum() / total), float(
        (sub > GOOD_EXPOSURE_FRACTION * p90).sum() / total
    )


def audit_object(row, folder, cosmo):
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

    out = {}
    flux_path = folder / "broad_flux.img"
    exp_path = folder / "broad_thresh.expmap"
    with fits.open(flux_path, memmap=True) as flux_hdul:
        header = flux_hdul[0].header
        wcs = WCS(header).celestial
        pixel_arcsec = float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600)
        out.update(
            naxis1=header["NAXIS1"],
            naxis2=header["NAXIS2"],
            pixel_arcsec=round(pixel_arcsec, 4),
            field_arcmin=round(
                max(header["NAXIS1"], header["NAXIS2"]) * pixel_arcsec / 60, 1
            ),
            bunit=header.get("BUNIT"),
            bkgsub=bool(header.get("BKGSUB")),
            exposure_ks=round(float(header.get("EXPOSURE", 0)) / 1e3, 2),
            chips=str(header.get("DETNAM", "")).replace("ACIS-", ""),
            datamode=header.get("DATAMODE"),
        )
        if pd.isna(row["center_ra"]):
            return out
        cx, cy = (
            float(v)
            for v in wcs.world_to_pixel(
                SkyCoord(row["center_ra"] * u.deg, row["center_dec"] * u.deg)
            )
        )
        out.update(center_x=round(cx, 1), center_y=round(cy, 1))
        # Pixel values in LEMUR's fixed 4.2' cutout around the X-ray center.
        half = ASTROCLIP_CUTOUT_PIX * ACIS_PIXEL_ARCSEC / pixel_arcsec / 2
        x0, x1 = max(0, int(cx - half)), min(header["NAXIS1"], int(cx + half))
        y0, y1 = max(0, int(cy - half)), min(header["NAXIS2"], int(cy + half))
        cut = np.asarray(flux_hdul[0].data[y0:y1, x0:x1], dtype=np.float64)
    finite = cut[np.isfinite(cut)]
    nonzero = finite[finite != 0]
    out.update(
        cutout_nan_pixels=int(cut.size - finite.size),
        cutout_frac_negative=round(
            float((nonzero < 0).mean()) if nonzero.size else np.nan, 3
        ),
        cutout_frac_zero=round(
            float((finite == 0).mean()) if finite.size else np.nan, 3
        ),
        cutout_flux_p50=float(np.percentile(nonzero, 50)) if nonzero.size else np.nan,
        cutout_flux_p99=float(np.percentile(nonzero, 99)) if nonzero.size else np.nan,
    )

    with fits.open(exp_path, memmap=True) as exp_hdul:
        exposure = exp_hdul[0].data
        stride = max(1, int(max(exposure.shape) / 1000))
        sample = np.asarray(exposure[::stride, ::stride], dtype=np.float64)
        positive = sample[sample > 0]
        p90 = float(np.percentile(positive, 90)) if positive.size else 0.0
        out["expmap_p90_cm2s"] = p90
        anyc, good = box_coverage(
            exposure,
            cx,
            cy,
            ASTROCLIP_CUTOUT_PIX * ACIS_PIXEL_ARCSEC / pixel_arcsec / 2,
            p90,
        )
        out.update(cov_astroclip_any=round(anyc, 3), cov_astroclip_good=round(good, 3))
        z = row["redshift"]
        if z is not None and np.isfinite(z) and z > 0:
            kpc_per_arcsec = float(
                cosmo.kpc_proper_per_arcmin(z).to(u.kpc / u.arcsec).value
            )
            out["kpc_per_arcsec"] = round(kpc_per_arcsec, 4)
            out["psf_kpc"] = round(0.5 * kpc_per_arcsec, 3)  # on-axis Chandra PSF ~0.5"
            for kpc in FIELDS_KPC:
                side_arcsec = kpc / kpc_per_arcsec
                anyc, good = box_coverage(
                    exposure, cx, cy, side_arcsec / pixel_arcsec / 2, p90
                )
                out[f"fov{kpc}_arcmin"] = round(side_arcsec / 60, 2)
                out[f"fov{kpc}_native_pix"] = int(
                    round(side_arcsec / ACIS_PIXEL_ARCSEC)
                )
                out[f"cov{kpc}_any"] = round(anyc, 3)
                out[f"cov{kpc}_good"] = round(good, 3)
    return out


def summarize(df):
    clusters = df[df["is_cluster"]]
    with_z = clusters[clusters["redshift"].fillna(0) > 0]

    def q(series, digits=2):
        s = series.dropna()
        return (
            [round(float(v), digits) for v in np.percentile(s, [5, 25, 50, 75, 95])]
            if len(s)
            else None
        )

    summary = {
        "objects": int(len(df)),
        "clusters": int(len(clusters)),
        "clusters_with_redshift": int(len(with_z)),
        "clusters_with_center": int(clusters["center_ra"].notna().sum()),
        "all_bkgsub": bool(df["bkgsub"].all()),
        "units": sorted(df["bunit"].dropna().unique().tolist()),
        "pixel_arcsec": sorted(df["pixel_arcsec"].dropna().unique().tolist()),
        "cluster_redshift_p5_25_50_75_95": q(with_z["redshift"], 3),
        "cluster_exposure_ks_p5_25_50_75_95": q(clusters["exposure_ks"], 1),
        "cluster_field_arcmin_p5_25_50_75_95": q(clusters["field_arcmin"], 1),
        "cluster_obsids_p5_25_50_75_95": q(clusters["n_obsids"], 0),
        "clusters_acis_i_only": int(
            ((clusters["n_acis_i"] > 0) & (clusters["n_acis_s"] == 0)).sum()
        ),
        "clusters_acis_s_only": int(
            ((clusters["n_acis_s"] > 0) & (clusters["n_acis_i"] == 0)).sum()
        ),
        "clusters_mixed_i_s": int(
            ((clusters["n_acis_i"] > 0) & (clusters["n_acis_s"] > 0)).sum()
        ),
        "cutout_frac_negative_median": round(
            float(clusters["cutout_frac_negative"].median()), 3
        ),
        "cutout_frac_zero_median": round(
            float(clusters["cutout_frac_zero"].median()), 3
        ),
        "cutout_nan_pixels_total": int(clusters["cutout_nan_pixels"].fillna(0).sum()),
        "astroclip_cutout_coverage_any_median": round(
            float(clusters["cov_astroclip_any"].median()), 3
        ),
    }
    for kpc in FIELDS_KPC:
        summary[f"fov{kpc}_arcmin_p5_25_50_75_95"] = q(with_z[f"fov{kpc}_arcmin"], 2)
        summary[f"fov{kpc}_native_pix_p5_50_95"] = [
            int(v)
            for v in np.percentile(with_z[f"fov{kpc}_native_pix"].dropna(), [5, 50, 95])
        ]
        for cut in (0.95, 0.8, 0.5):
            summary[f"fov{kpc}_clusters_cov_good_ge_{cut}"] = int(
                (with_z[f"cov{kpc}_good"] >= cut).sum()
            )
    summary["psf_kpc_p5_50_95"] = q(with_z["psf_kpc"], 2)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--out", default=str(ROOT / "outputs" / "audit"))
    parser.add_argument("--limit", type=int, help="Only the first N objects (testing)")
    args = parser.parse_args(argv)

    from astropy.cosmology import Planck18

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(args.db)
    if args.limit:
        catalog = catalog.head(args.limit)
    records = []
    for i, row in catalog.iterrows():
        record = row.to_dict()
        folder = resolve_folder(args.data_dir, row["Name"])
        if folder is None:
            record["problem"] = "no image"
        else:
            try:
                record.update(audit_object(row, folder, Planck18))
            except Exception as exc:
                record["problem"] = f"{type(exc).__name__}: {exc}"
        records.append(record)
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(catalog)}", flush=True)
    df = pd.DataFrame(records)
    df.to_csv(out_dir / "lemur_audit.csv", index=False)
    summary = summarize(df)
    summary["problems"] = (
        df["problem"].dropna().tolist()[:20] if "problem" in df else []
    )
    (out_dir / "lemur_audit_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
