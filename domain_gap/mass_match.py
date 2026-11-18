"""Mass-matched comparison of LEMUR and the TNG mocks.

    python -m domain_gap.mass_match [--runs outputs/embeddings/<config> ...]
        [--out outputs/figures/mass]

LEMUR has no masses, so the same mass proxy is measured on both sides and the
mocks, whose M500 is known, calibrate it:

1. Luminosity proxy: the X-ray photon luminosity (0.5-7 keV, observed frame,
   photons s^-1) within r < 250 kpc of the centre, from the 500 kpc stage-1
   extraction of every image (coverage-weighted mean surface brightness times
   the aperture area, times 4 pi D_L^2). Images whose aperture is < 90% covered
   get no value. Identical code for LEMUR and the mocks.
2. Calibration: at each mock redshift, log M500 = a + b log L fitted to the
   mocks (both simulations, all projections and exposures); applied to LEMUR
   clusters within +-0.025 in redshift, this gives a TNG-calibrated M500. It
   assumes TNG's L-M relation (and its scatter) holds for real clusters.
3. Matching by reweighting: at each redshift the mocks of one simulation are
   weighted so that their distribution in (log L bin of ``--bin-dex``, exposure)
   equals LEMUR's, with each LEMUR cluster assigned the mock exposure (20 or
   100 ks) nearest its own. LEMUR clusters in bins without mocks are left out
   (and counted). Reweighting, unlike nearest-neighbour matching, keeps the two
   distributions equal even where one sample is sparse.
4. Domain AUC (grouped cross-validation, as in analyze_embeddings, with the
   weights in the fit and the AUC) against the unweighted AUC; and TNG300
   reweighted to TNG-Cluster in true M500, which tests whether mass drives the
   simulation-to-simulation separation.

Outputs: luminosities.csv (cached), lm_relation.png, masses.png,
matched_auc.png, matched_auc.csv, lemur_masses.csv.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import analyze_embeddings as ae
from . import preprocess, spatial
from .plotting import save_figure

ROOT = Path(__file__).resolve().parents[1]
APERTURE_KPC = 250.0
MIN_APERTURE_COVERAGE = 0.9
COLORS = ae.COLORS


# ---------------------------------------------------------------- luminosity


def aperture_flux(sb, coverage, field_kpc, field_arcsec, radius_kpc=APERTURE_KPC):
    """(photon flux in ph cm^-2 s^-1 within radius_kpc, covered fraction)."""
    grid = sb.shape[0]
    yy, xx = np.indices(sb.shape)
    r_kpc = np.hypot(xx - (grid - 1) / 2, yy - (grid - 1) / 2) * field_kpc / grid
    aperture = r_kpc < radius_kpc
    weight = np.where(aperture, coverage, 0.0)
    covered = weight.sum() / aperture.sum()
    if covered < MIN_APERTURE_COVERAGE:
        return np.nan, float(covered)
    mean_sb = (sb * weight).sum() / weight.sum()
    pixel_arcsec2 = (field_arcsec / grid) ** 2
    return float(mean_sb * aperture.sum() * pixel_arcsec2), float(covered)


def luminosities(config_path, cache):
    """Photon luminosity within APERTURE_KPC for every extracted image (cached)."""
    if Path(cache).exists():
        return pd.read_csv(cache)
    cfg = preprocess.load_config(config_path)
    if cfg["field"].get("kpc", 0) < 2 * APERTURE_KPC:
        raise ValueError("the aperture must fit in the config's physical field")
    base = Path(cfg.get("stage1_dir", preprocess.PREPROCESSED / "_stage1")) / preprocess.spatial_hash(cfg)
    cosmo = spatial.cosmology(cfg.get("cosmology", "Planck15"))
    rows = []
    for source_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for path in sorted(source_dir.glob("*.npz")):
            with np.load(path) as data:
                info = json.loads(str(data["info"]))
                if info.get("status") != "ok":
                    continue
                flux, covered = aperture_flux(
                    data["sb"], data["coverage"], info["field_kpc"], info["field_arcsec"]
                )
            d_l = cosmo.luminosity_distance(info["redshift"]).to("cm").value
            rows.append(
                {
                    "source": info["source"],
                    "name": info["name"],
                    "redshift": info["redshift"],
                    "aperture_coverage": covered,
                    "flux_ph": flux,
                    "log_L_ph": np.log10(4 * np.pi * d_l**2 * flux) if flux > 0 else np.nan,
                }
            )
    df = pd.DataFrame(rows)
    Path(cache).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


# ---------------------------------------------------------------- calibration


def fit_lm(mocks):
    """log M500 = a + b (log L - pivot) by least squares; returns (a, b, pivot, scatter)."""
    x = mocks["log_L_ph"].to_numpy()
    y = np.log10(mocks["M500c_Msun"].to_numpy())
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    pivot = float(np.median(x))
    b, a = np.polyfit(x - pivot, y, 1)
    scatter = float(np.std(y - (a + b * (x - pivot))))
    return float(a), float(b), pivot, scatter


# ---------------------------------------------------------------- matching


def nearest_exposure(exposure_ks, choices):
    choices = np.asarray(sorted(choices))
    return float(choices[np.argmin(np.abs(np.log(choices) - np.log(max(exposure_ks, 1e-3))))])


def reweight(target_values, target_class, other_values, other_class, bin_dex, return_keys=False):
    """Weights making ``other`` follow ``target``'s distribution in (value bin, class).

    Returns (target weights, other weights): target rows whose bin has no
    ``other`` rows get 0 (no counterpart), the rest 1; other rows get
    n_target(bin) / n_other(bin), or 0 where the target has none.
    """
    def keys(values, classes):
        return [
            (int(np.floor(v / bin_dex)), c) if np.isfinite(v) else None
            for v, c in zip(values, classes)
        ]

    kt, ko = keys(target_values, target_class), keys(other_values, other_class)
    nt = pd.Series([k for k in kt if k is not None]).value_counts().to_dict()
    no = pd.Series([k for k in ko if k is not None]).value_counts().to_dict()
    wt = np.array([1.0 if k is not None and k in no else 0.0 for k in kt])
    wo = np.array([nt[k] / no[k] if k is not None and k in nt else 0.0 for k in ko])
    if return_keys:
        return wt, wo, list(kt) + list(ko)
    return wt, wo


def n_eff(w):
    """Kish effective sample size of weights."""
    w = np.asarray(w, float)
    return float(w.sum() ** 2 / (w**2).sum()) if (w > 0).any() else 0.0


# ---------------------------------------------------------------- analysis


def _weighted_auc(x, a, b, wa, wb, strata=None):
    return _weighted_auc_ci(x, a, b, wa, wb, n_boot=0, strata=strata)[0]


def _weighted_auc_ci(x, a, b, wa, wb, n_boot=1000, strata=None):
    """(AUC, 68% low, 68% high) of sample a against b with weights.

    ``strata``: the reweighting bin of each row (a's rows, then b's), so that
    the classes are rebalanced within bins in every training fold."""
    rows = np.r_[a["row"], b["row"]]
    labels = np.r_[np.ones(len(a)), np.zeros(len(b))]
    groups = np.r_[a["group"], b["group"]]
    if n_boot == 0:
        return ae.domain_auc(x[rows], labels, groups, weights=np.r_[wa, wb], strata=strata), np.nan, np.nan
    return ae.domain_auc_ci(x[rows], labels, groups, weights=np.r_[wa, wb], n_boot=n_boot, strata=strata)


def _ci_columns(prefix, value):
    return {prefix: value[0], f"{prefix}_lo": value[1], f"{prefix}_hi": value[2]}


def matched_aucs(runs, lum, bin_dex):
    rows, lemur_masses = [], []
    for df, x, name in runs:
        df = df.merge(lum[["source", "name", "log_L_ph"]], on=["source", "name"], how="left")
        for z in ae.mock_redshifts(df):
            idx = ae.matched(df, z)
            sub = df.iloc[idx].copy()
            sub["row"] = idx
            lemur = sub[sub["source"] == "LEMUR"]
            mocks = sub[sub["source"] != "LEMUR"]
            exposures = sorted(mocks["exposure_ks"].unique())
            lemur_class = [nearest_exposure(e, exposures) for e in lemur["exposure_ks"]]
            for sim in ["TNG300-1", "TNG-Cluster"]:
                s = mocks[mocks["source"] == sim]
                before = _weighted_auc_ci(x, lemur, s, np.ones(len(lemur)), np.ones(len(s)))
                wl, ws, keys = reweight(lemur["log_L_ph"], lemur_class, s["log_L_ph"], s["exposure_ks"], bin_dex, return_keys=True)
                rows.append(
                    {
                        "config": name, "redshift": z, "pair": f"LEMUR vs {sim}",
                        "matched_on": "L(<250 kpc), exposure",
                        **_ci_columns("auc_all", before),
                        **_ci_columns("auc_matched", _weighted_auc_ci(x, lemur, s, wl, ws, strata=keys)),
                        "n_a": len(lemur), "n_a_matched": int(wl.sum()),
                        "n_b": len(s), "n_eff_b": round(n_eff(ws), 1),
                    }
                )
            # Simulation vs simulation on true M500: TNG300 reweighted to TNG-Cluster.
            tng300 = mocks[mocks["source"] == "TNG300-1"]
            cluster = mocks[mocks["source"] == "TNG-Cluster"]
            before = _weighted_auc_ci(x, cluster, tng300, np.ones(len(cluster)), np.ones(len(tng300)))
            wc, wt, keys = reweight(
                np.log10(cluster["M500c_Msun"]), cluster["exposure_ks"],
                np.log10(tng300["M500c_Msun"]), tng300["exposure_ks"], bin_dex, return_keys=True,
            )
            rows.append(
                {
                    "config": name, "redshift": z, "pair": "TNG-Cluster vs TNG300-1",
                    "matched_on": "true M500, exposure",
                    **_ci_columns("auc_all", before),
                    **_ci_columns("auc_matched", _weighted_auc_ci(x, cluster, tng300, wc, wt, strata=keys)),
                    "n_a": len(cluster), "n_a_matched": int(wc.sum()),
                    "n_b": len(tng300), "n_eff_b": round(n_eff(wt), 1),
                }
            )
            if name == runs[0][2]:
                a, b, pivot, scatter = fit_lm(mocks)
                est = lemur.assign(
                    log_M500_est=a + b * (lemur["log_L_ph"] - pivot), lm_scatter_dex=scatter, z_bin=z
                )
                lemur_masses.append(
                    est[["name", "redshift", "exposure_ks", "z_bin", "log_L_ph", "log_M500_est", "lm_scatter_dex"]]
                )
    masses = pd.concat(lemur_masses) if lemur_masses else pd.DataFrame()
    return pd.DataFrame(rows), masses


# ---------------------------------------------------------------- figures


def lm_figure(df, lum, out):
    import matplotlib.pyplot as plt

    df = df.merge(lum[["source", "name", "log_L_ph"]], on=["source", "name"], how="left")
    zs = ae.mock_redshifts(df)
    fig, axes = plt.subplots(1, len(zs), figsize=(4.4 * len(zs), 3.8), squeeze=False, sharey=True)
    for ax, z in zip(axes[0], zs):
        sub = df.iloc[ae.matched(df, z)]
        mocks = sub[sub["source"] != "LEMUR"]
        for sim in ["TNG300-1", "TNG-Cluster"]:
            s = mocks[mocks["source"] == sim]
            ax.scatter(s["log_L_ph"], np.log10(s["M500c_Msun"]), s=4, alpha=0.3, c=COLORS[sim], label=sim, linewidths=0)
        a, b, pivot, scatter = fit_lm(mocks)
        xs = np.linspace(np.nanmin(mocks["log_L_ph"]), np.nanmax(mocks["log_L_ph"]), 20)
        ax.plot(xs, a + b * (xs - pivot), "k-", lw=1, label=f"fit: slope {b:.2f}, scatter {scatter:.2f} dex")
        lemur_l = sub.loc[sub["source"] == "LEMUR", "log_L_ph"].dropna()
        ax.plot(lemur_l, np.full(len(lemur_l), ax.get_ylim()[0] + 0.02), "|", color="k", ms=10, alpha=0.6, label=f"LEMUR L ({len(lemur_l)})")
        ax.set_title(f"z = {z:.2f}", fontsize=9)
        ax.set_xlabel(r"log $L_{\rm ph}$(<250 kpc) [ph s$^{-1}$]")
        ax.legend(fontsize=6.5)
    axes[0, 0].set_ylabel(r"log $M_{500}$ [M$_\odot$]")
    fig.tight_layout()
    save_figure(fig, out / "lm_relation.png")
    plt.close(fig)


def mass_figure(df, masses, out):
    import matplotlib.pyplot as plt

    zs = sorted(masses["z_bin"].unique())
    fig, axes = plt.subplots(1, len(zs), figsize=(4.4 * len(zs), 3.4), squeeze=False, sharey=True)
    bins = np.linspace(12.5, 15.6, 32)
    for ax, z in zip(axes[0], zs):
        sub = df[(df["source"] != "LEMUR") & (df["redshift"] == z)].drop_duplicates(["source", "halo_id"])
        for sim in ["TNG300-1", "TNG-Cluster"]:
            s = np.log10(sub.loc[sub["source"] == sim, "M500c_Msun"])
            ax.hist(s, bins, histtype="step", density=True, color=COLORS[sim], label=f"{sim} ({len(s)} halos)")
        est = masses.loc[masses["z_bin"] == z, "log_M500_est"].dropna()
        ax.hist(est, bins, histtype="step", density=True, color="k", lw=1.5, label=f"LEMUR, TNG-calibrated ({len(est)})")
        ax.set_title(f"z = {z:.2f} (LEMUR within ±0.025)", fontsize=9)
        ax.set_xlabel(r"log $M_{500}$ [M$_\odot$]")
        ax.legend(fontsize=6.5)
    fig.tight_layout()
    save_figure(fig, out / "masses.png")
    plt.close(fig)


def auc_figure(table, out):
    import matplotlib.pyplot as plt

    pairs = list(dict.fromkeys(table["pair"]))
    configs = list(dict.fromkeys(table["config"]))
    zs = sorted(table["redshift"].unique())
    fig, axes = plt.subplots(len(pairs), len(configs), figsize=(3.8 * len(configs), 2.9 * len(pairs)), squeeze=False, sharey=True)
    for r, pair in enumerate(pairs):
        for c, config in enumerate(configs):
            ax = axes[r, c]
            sel = table[(table["pair"] == pair) & (table["config"] == config)].set_index("redshift")
            pos = np.arange(len(zs))
            for shift, key, color, label in [(-0.2, "auc_all", "0.6", "all"), (0.2, "auc_matched", "tab:green", "mass-matched")]:
                v = np.array([sel[key].get(z, np.nan) for z in zs])
                err = np.array([[v[i] - sel[f"{key}_lo"].get(z, np.nan), sel[f"{key}_hi"].get(z, np.nan) - v[i]] for i, z in enumerate(zs)]).T
                ax.bar(pos + shift, v, 0.4, color=color, label=label, yerr=err, capsize=2, ecolor="k", error_kw={"lw": 0.8})
            ax.axhline(0.5, color="gray", lw=0.8, ls="--")
            ax.set_xticks(pos, [f"z={z:.2f}" for z in zs], fontsize=8)
            ax.set_ylim(0.4, 1.0)
            ax.set_title(f"{config}\n{pair}", fontsize=8)
    axes[0, 0].legend(fontsize=7)
    for r in range(len(pairs)):
        axes[r, 0].set_ylabel("domain AUC")
    fig.tight_layout()
    save_figure(fig, out / "matched_auc.png")
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default_runs = [str(p) for p in sorted((ROOT / "outputs" / "embeddings").glob("*")) if (p / "run.json").exists()]
    parser.add_argument("--runs", nargs="*", default=default_runs)
    parser.add_argument("--luminosity-config", default=str(ROOT / "configs" / "harmonized_morphology.yaml"))
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "mass"))
    parser.add_argument(
        "--luminosity-cache", default=str(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    )
    parser.add_argument("--bin-dex", type=float, default=0.1, help="Bin width of the reweighting (dex)")
    parser.add_argument("--probe", choices=["linear", "mlp"], default="linear",
                        help="Domain classifier; a non-default probe writes to <out>_<probe>")
    ae.add_signal_args(parser)
    args = parser.parse_args(argv)
    ae.PROBE = args.probe
    out = Path(args.out + ("" if args.probe == "linear" else f"_{args.probe}"))
    out.mkdir(parents=True, exist_ok=True)
    lum = luminosities(args.luminosity_config, args.luminosity_cache)
    print(f"Luminosities: {lum['log_L_ph'].notna().sum()} of {len(lum)} images")
    runs = [ae.load_run(r, ae.signal_cut(args)) for r in args.runs]
    table, masses = matched_aucs(runs, lum, args.bin_dex)
    table.to_csv(out / "matched_auc.csv", index=False)
    masses.to_csv(out / "lemur_masses.csv", index=False)
    lm_figure(runs[0][0], lum, out)
    mass_figure(runs[0][0], masses, out)
    auc_figure(table, out)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"Figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
