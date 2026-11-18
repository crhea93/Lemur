"""Central point sources (AGN) and the core concentration with point sources masked.

    python -m domain_gap.agn measure [--workers 6]   # native-resolution measurements (cached)
    python -m domain_gap.agn analyse                  # high-c fractions with bootstrap intervals

The mocks contain no AGN, so a central AGN in a LEMUR cluster raises its
concentration c without a cool core. A point source is unresolved (the PSF,
~1-2" near the aimpoint); a cool core is resolved over many arcseconds. On the
native-resolution flux images, around the same centres as preprocessing, we
measure for every image:

- spike = surface brightness within 1.5" / that between 1.5" and 4" around
  the brightest point within 15" of the centre (after 1" smoothing; the
  centre itself is the diffuse peak, found with point sources masked): a PSF
  spike on top of a smooth core. The mocks, observed through the same PSF
  but without AGN, give its distribution for pure cluster cores at each
  redshift and exposure; LEMUR clusters above the mocks' 99th percentile (and
  with at least 20 counts within 4") are flagged as hosting a central point
  source;
- c_masked = F(<40 kpc) / F(<250 kpc) summed over pixels outside 3" of that
  brightest point and outside point sources detected (LEMUR's detector) more than 10" from
  the centre; and c_native, the same without masking, as a check against the
  preprocessing c.

``analyse`` compares the fraction of clusters with c > 0.15 between LEMUR (all,
in Planck PSZ2, not in PSZ2) and the mocks reweighted to each LEMUR subsample's
(log L, exposure), for c, c_masked and c with flagged clusters removed, with
bootstrap 68% intervals (clusters and mock halos resampled) and a one-sided
bootstrap p-value for LEMUR exceeding the mocks. The signal cut is applied.
"""

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import io, spatial
from .plotting import save_figure
from .signal import _box, _read_box

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "agn"
R_SPIKE_IN, R_SPIKE_OUT = 1.5, 4.0
R_MASK_CENTRE, R_KEEP_SOURCES = 3.0, 10.0
R_PEAK_SEARCH = 15.0
CORE_KPC, OUTER_KPC = 40.0, 250.0
MARGIN_ARCSEC = 120.0
C_HIGH = 0.15
MIN_CENTRAL_COUNTS = 20


# ---------------------------------------------------------------- measurement


def _crop(row):
    """(counts, flux, weight, centre in crop pixels, pixel arcsec) around the image's centre."""
    from astropy.io import fits
    from astropy.wcs import WCS

    radius = spatial.field_side_arcsec({"kpc": 2 * OUTER_KPC}, row["redshift"]) / 2
    if row["source"] == io.LEMUR:
        folder = Path(row["folder"])
        counts_path = io._existing(folder / "broad_thresh.img", folder / "broad_thresh.img.gz")
        flux_path, weight_path = io.lemur_files(folder, "broad")
        header = fits.getheader(flux_path)
        wcs = WCS(header).celestial
        pix = io._pixel_arcsec(wcs)
        cx, cy = wcs.wcs_world2pix([[row["center_ra"], row["center_dec"]]], 0)[0]
        y0, y1, x0, x1 = _box((cx, cy), (radius + MARGIN_ARCSEC) / pix, (header["NAXIS2"], header["NAXIS1"]))
        counts, flux, weight = (_read_box(p, y0, y1, x0, x1) for p in (counts_path, flux_path, weight_path))
    else:
        from .mocks import observe

        obs = Path(row["folder"])
        counts_full, header = fits.getdata(obs / "broad_counts.fits.gz", header=True)
        flux_full = fits.getdata(obs / "broad_flux.fits.gz")
        _, expmap_per_s = observe.load_reference(obs.parents[4] / "reference", "broad")
        wcs = WCS(header).celestial
        pix = io._pixel_arcsec(wcs)
        cx, cy = wcs.wcs_world2pix([[row["center_ra"], row["center_dec"]]], 0)[0]
        y0, y1, x0, x1 = _box((cx, cy), (radius + MARGIN_ARCSEC) / pix, counts_full.shape)
        counts = np.asarray(counts_full[y0:y1, x0:x1], np.float64)
        flux = np.asarray(flux_full[y0:y1, x0:x1], np.float64)
        weight = float(header["EXPOSURE"]) * expmap_per_s[y0:y1, x0:x1]
    return counts, flux, weight, (cx - x0, cy - y0), pix, radius


def measure_one(row):
    script = io.astroclip_script()
    counts, flux, weight, (cx, cy), pix, radius = _crop(row)
    covered = weight > 0
    yy, xx = np.indices(flux.shape)
    r_arcsec = np.hypot(xx - cx, yy - cy) * pix
    kpc_per_arcsec = 2 * OUTER_KPC / (2 * radius)

    def mean_sb(sel):
        sel = sel & covered
        w = weight[sel].sum()
        return (flux[sel] * weight[sel]).sum() / w if w > 0 else np.nan

    # The centre ignores point sources (it is the diffuse peak), so an AGN can sit a
    # few arcsec away: measure the spike at the brightest point within 15" of it,
    # after smoothing on the PSF scale (1").
    from scipy.ndimage import gaussian_filter

    smooth = gaussian_filter(np.where(covered, np.nan_to_num(flux), 0.0), 1.0 / pix)
    near = covered & (r_arcsec < R_PEAK_SEARCH)
    if near.any():
        py, px = np.unravel_index(np.argmax(np.where(near, smooth, -np.inf)), flux.shape)
    else:
        py, px = int(round(cy)), int(round(cx))
    r_peak = np.hypot(xx - px, yy - py) * pix
    spike = mean_sb(r_peak < R_SPIKE_IN) / mean_sb((r_peak >= R_SPIKE_IN) & (r_peak < R_SPIKE_OUT))
    # Point sources on the 3.9" working grid, mapped back to native pixels.
    factor = max(1, int(round(script.WORK_PIXEL_ARCSEC / pix)))
    binned = script._block_reduce(np.nan_to_num(flux), factor, np.mean)
    exp = script._block_reduce(np.nan_to_num(weight), factor, np.mean)
    positive = exp[exp > 0]
    sources = np.zeros_like(flux, bool)
    if positive.size:
        mask = exp > script.EXPOSURE_FRACTION * np.percentile(positive, 90)
        found = script._point_source_mask(binned, mask, pix * factor)
        up = np.repeat(np.repeat(found, factor, axis=0), factor, axis=1)
        sources[: up.shape[0], : up.shape[1]] = up[: flux.shape[0], : flux.shape[1]]
    r_kpc = r_arcsec * kpc_per_arcsec
    keep = covered & ~((r_peak < R_MASK_CENTRE) | (sources & (r_arcsec > R_KEEP_SOURCES)))

    def ratio(sel):
        outer = flux[sel & (r_kpc < OUTER_KPC)].sum()
        return flux[sel & (r_kpc < CORE_KPC)].sum() / outer if outer > 0 else np.nan

    return {
        "source": row["source"], "name": row["name"],
        "spike": float(spike),
        "central_counts": float(counts[(r_peak < R_SPIKE_OUT) & covered].sum()),
        "peak_offset_arcsec": float(np.hypot(px - cx, py - cy) * pix),
        "c_native": float(ratio(covered)),
        "c_masked": float(ratio(keep)),
        "masked_fraction_core": float(1 - keep[(r_kpc < CORE_KPC) & covered].mean()) if ((r_kpc < CORE_KPC) & covered).any() else np.nan,
        "status": "ok",
    }


def _task(row):
    try:
        return measure_one(row)
    except Exception as exc:  # recorded, not fatal
        return {"source": row["source"], "name": row["name"], "status": f"error: {type(exc).__name__}: {exc}"}


def measure(args):
    cache = OUT / "agn.csv"
    if cache.exists() and not args.force:
        print(f"{cache} exists (use --force to remeasure)")
        return
    man = pd.read_parquet(ROOT / "outputs" / "embeddings" / "harmonized_physical" / "manifest.parquet")
    man = man[(man["status"] == "ok") & man["redshift"].notna()]
    rows = man[["source", "name", "folder", "center_ra", "center_dec", "redshift"]].to_dict("records")
    print(f"Measuring {len(rows)} images", flush=True)
    with ProcessPoolExecutor(args.workers) as pool:
        result = pd.DataFrame(list(pool.map(_task, rows, chunksize=16)))
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache, index=False)
    print(result["status"].str.slice(0, 60).value_counts().to_string())


# ---------------------------------------------------------------- analysis


def load_table():
    from . import analyze_embeddings as ae
    from .selection import lemur_table

    man = pd.read_parquet(ROOT / "outputs" / "embeddings" / "harmonized_physical" / "manifest.parquet")
    sig = pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv")
    lum = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    agn = pd.read_csv(OUT / "agn.csv")
    df, _, _ = ae.load_run(ROOT / "outputs" / "embeddings" / "harmonized_physical", (sig, 10.0, 0.5))
    df = df.merge(lum[["source", "name", "log_L_ph"]], on=["source", "name"], how="left")
    df = df.merge(core, on=["source", "name"], how="left").merge(agn, on=["source", "name"], how="left")
    cat = lemur_table(ROOT / "outputs" / "embeddings" / "harmonized_physical" / "manifest.parquet")
    df = df.merge(cat[["name", "in_psz2"]], on="name", how="left")
    return df


def flag_central_sources(df):
    """Flag LEMUR images whose spike exceeds the mocks' 99th percentile at their z and exposure."""
    from . import mass_match as mm

    df = df.copy()
    df["central_ps"] = False
    mocks = df[df["source"] != "LEMUR"]
    limits = mocks.groupby(["redshift", "exposure_ks"])["spike"].quantile(0.99)
    for z in sorted(mocks["redshift"].unique()):
        near = (df["source"] == "LEMUR") & ((df["redshift"] - z).abs() < 0.025 + 1e-9)
        exposures = sorted(mocks.loc[mocks["redshift"] == z, "exposure_ks"].unique())
        for i in np.where(near)[0]:
            row = df.iloc[i]
            limit = limits.loc[(z, mm.nearest_exposure(row["exposure_ks"], exposures))]
            df.iloc[i, df.columns.get_loc("central_ps")] = bool(
                row["spike"] > limit and row["central_counts"] >= MIN_CENTRAL_COUNTS
            )
    return df


def high_c_fraction(values, weights=None):
    v = np.asarray(values, float)
    w = np.ones(len(v)) if weights is None else np.asarray(weights, float)
    ok = np.isfinite(v) & (w > 0)
    return float(np.average(v[ok] > C_HIGH, weights=w[ok])) if ok.any() else np.nan


def bootstrap_difference(lemur_c, mock_c, mock_w, mock_groups, n_boot=2000, seed=0):
    """68% intervals of the LEMUR and mock high-c fractions and one-sided p(LEMUR <= mocks)."""
    rng = np.random.default_rng(seed)
    lemur_c = np.asarray(lemur_c, float)
    groups = pd.Series(np.arange(len(mock_c))).groupby(np.asarray(mock_groups)).apply(list).tolist()
    fl, fm = [], []
    for _ in range(n_boot):
        li = rng.integers(0, len(lemur_c), len(lemur_c))
        gi = rng.integers(0, len(groups), len(groups))
        mi = np.concatenate([groups[g] for g in gi])
        fl.append(high_c_fraction(lemur_c[li]))
        fm.append(high_c_fraction(np.asarray(mock_c)[mi], np.asarray(mock_w)[mi]))
    fl, fm = np.array(fl), np.array(fm)
    diff = fl - fm
    return {
        "lemur_lo": np.nanpercentile(fl, 16), "lemur_hi": np.nanpercentile(fl, 84),
        "mock_lo": np.nanpercentile(fm, 16), "mock_hi": np.nanpercentile(fm, 84),
        "p_lemur_not_higher": float(np.nanmean(diff <= 0)),
    }


def analyse(args):
    from . import analyze_embeddings as ae
    from . import core as core_mod
    from . import mass_match as mm

    df = flag_central_sources(load_table())
    rows = []
    variants = [("c", "c40_250", False), ("c_masked", "c_masked", False), ("c, central point sources removed", "c40_250", True)]
    for z in ae.mock_redshifts(df):
        near = df[(df["source"] == "LEMUR") & ((df["redshift"] - z).abs() < ae.Z_WIDTH + 1e-9)]
        exposures = sorted(df.loc[(df["source"] != "LEMUR") & (df["redshift"] == z), "exposure_ks"].unique())
        subsets = {"all": near, "in PSZ2": near[near["in_psz2"] == True], "not in PSZ2": near[near["in_psz2"] != True]}  # noqa: E712
        for label, lemur in subsets.items():
            for variant, col, drop_flagged in variants:
                l = lemur[~lemur["central_ps"]] if drop_flagged else lemur
                if len(l) < 5:
                    continue
                cls = [mm.nearest_exposure(e, exposures) for e in l["exposure_ks"]]
                mocks = df[(df["source"] != "LEMUR") & (df["redshift"] == z)]
                wl, wm = core_mod.reweight_nd([l["log_L_ph"]], cls, [mocks["log_L_ph"]], mocks["exposure_ks"], [0.2])
                keep = wl > 0
                fl = high_c_fraction(l[col][keep])
                fm = high_c_fraction(mocks[col], wm)
                boot = bootstrap_difference(l[col][keep].to_numpy(), mocks[col].to_numpy(), wm, mocks["group"].to_numpy())
                rows.append({"redshift": z, "lemur": label, "variant": variant, "n_lemur": int(keep.sum()),
                             "n_flagged": int(lemur["central_ps"].sum()), "lemur_frac": fl, "mock_frac": fm, **boot})
    table = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "high_c_fractions.csv", index=False)
    lemur = df[df["source"] == "LEMUR"]
    hi = lemur["c40_250"] > C_HIGH
    summary = {
        "lemur_flagged": int(lemur["central_ps"].sum()), "lemur_with_spike": int(lemur["spike"].notna().sum()),
        "high_c_flagged": int((hi & lemur["central_ps"]).sum()), "high_c": int(hi.sum()),
        "rho_c_vs_c_masked_lemur": float(lemur[["c40_250", "c_masked"]].corr(method="spearman").iloc[0, 1]),
        "rho_c_vs_c_native_all": float(df[["c40_250", "c_native"]].corr(method="spearman").iloc[0, 1]),
    }
    pd.Series(summary).to_csv(OUT / "summary.csv")
    print(pd.Series(summary).to_string())
    show = table.assign(lemur=lambda t: t["lemur"].str.slice(0, 12), variant=lambda t: t["variant"].str.slice(0, 24))
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    figure(df, table)


def figure(df, table):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
    ax = axes[0]
    bins = np.logspace(-0.5, 1.3, 40)
    for source, color in [("LEMUR", "k"), ("TNG300-1", "tab:blue"), ("TNG-Cluster", "tab:red")]:
        s = df.loc[(df["source"] == source) & (df["central_counts"] >= MIN_CENTRAL_COUNTS), "spike"].dropna()
        ax.hist(s.clip(bins[0], bins[-1]), bins, histtype="step", density=True, color=color, label=f"{source} ({len(s)})")
    ax.set_xscale("log")
    ax.set_xlabel('central spike: SB(<1.5") / SB(1.5"-4")')
    ax.legend(fontsize=7)
    ax = axes[1]
    t = table[table["lemur"] == "all"]
    zs = sorted(t["redshift"].unique())
    variants = list(dict.fromkeys(t["variant"]))
    width = 0.8 / (len(variants) + 1)
    for i, variant in enumerate(variants):
        v = t[t["variant"] == variant].set_index("redshift")
        x = np.arange(len(zs)) + i * width
        ax.errorbar(x, [v.loc[z, "lemur_frac"] for z in zs],
                    yerr=[[v.loc[z, "lemur_frac"] - v.loc[z, "lemur_lo"] for z in zs], [v.loc[z, "lemur_hi"] - v.loc[z, "lemur_frac"] for z in zs]],
                    fmt="o", ms=4, capsize=2, label=f"LEMUR, {variant}")
    m = t[t["variant"] == "c"].set_index("redshift")
    ax.errorbar(np.arange(len(zs)) + len(variants) * width, [m.loc[z, "mock_frac"] for z in zs],
                yerr=[[m.loc[z, "mock_frac"] - m.loc[z, "mock_lo"] for z in zs], [m.loc[z, "mock_hi"] - m.loc[z, "mock_frac"] for z in zs]],
                fmt="s", color="0.4", ms=4, capsize=2, label="L-matched mocks, c")
    ax.set_xticks(np.arange(len(zs)) + width * len(variants) / 2, [f"z={z:g}" for z in zs])
    ax.set_ylabel(f"fraction with c > {C_HIGH}")
    ax.legend(fontsize=6.5)
    fig.tight_layout()
    save_figure(fig, OUT / "agn_check.png")
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--workers", type=int, default=6)
    m.add_argument("--force", action="store_true")
    sub.add_parser("analyse")
    args = parser.parse_args(argv)
    {"measure": measure, "analyse": analyse}[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
