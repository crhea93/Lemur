"""Core structure: surface-brightness concentration of LEMUR and the mocks.

    python -m domain_gap.core [--out outputs/figures/core]

- c = F(< 40 kpc) / F(< 250 kpc), the cool-core concentration of Santos et
  al. (2008) with the outer radius set by the 500 kpc stage-1 field (they use
  400 kpc, so their thresholds do not carry over), and the mean surface
  brightness within 40 kpc. Measured identically on every image from the
  stage-1 extraction around the X-ray peak.
- core_validation.png: c against the central cooling time of the TNG-Cluster
  halos (CCcriteria), to check that c traces cool cores in the simulation.
- core_distributions.png: c of LEMUR and of the mocks reweighted to LEMUR's
  (L, exposure) distribution, at each mock redshift.
- core_auc.png / core_auc.csv: domain AUC with the mocks reweighted to LEMUR
  in (L, exposure) and in (L, c, exposure), on the same coarse bins. If adding
  c moves the AUC towards 0.5, the remaining gap is mostly core structure.

The signal cut of domain_gap.signal is applied (a central AGN raises c);
--no-signal-cut turns it off.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import analyze_embeddings as ae
from . import mass_match as mm
from . import preprocess
from .plotting import save_figure

ROOT = Path(__file__).resolve().parents[1]
CORE_KPC = 40.0
OUTER_KPC = 250.0
COLORS = ae.COLORS


def concentration(sb, coverage, field_kpc):
    """(c, mean surface brightness within CORE_KPC), or NaNs if poorly covered."""
    grid = sb.shape[0]
    yy, xx = np.indices(sb.shape)
    r = np.hypot(xx - (grid - 1) / 2, yy - (grid - 1) / 2) * field_kpc / grid
    out = []
    for radius in (CORE_KPC, OUTER_KPC):
        ap = r < radius
        w = np.where(ap, coverage, 0.0)
        if w.sum() / ap.sum() < mm.MIN_APERTURE_COVERAGE:
            return np.nan, np.nan
        # Flux of the full aperture: coverage-weighted mean times its area.
        out.append((sb * w).sum() / w.sum() * ap.sum())
    core, outer = out
    core_sb = core / ((r < CORE_KPC).sum())
    return (core / outer if outer > 0 else np.nan), core_sb


def measure(config_path, cache):
    if Path(cache).exists():
        return pd.read_csv(cache)
    cfg = preprocess.load_config(config_path)
    base = Path(cfg.get("stage1_dir", preprocess.PREPROCESSED / "_stage1")) / preprocess.spatial_hash(cfg)
    rows = []
    for source_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for path in sorted(source_dir.glob("*.npz")):
            with np.load(path) as data:
                info = json.loads(str(data["info"]))
                if info.get("status") != "ok":
                    continue
                c, core_sb = concentration(data["sb"], data["coverage"], info["field_kpc"])
            rows.append({"source": info["source"], "name": info["name"], "c40_250": c, "sb40": core_sb})
    df = pd.DataFrame(rows)
    Path(cache).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def reweight_nd(target_values, target_class, other_values, other_class, bins, return_keys=False):
    """As mass_match.reweight, on several variables (lists of arrays, bin widths).

    ``return_keys`` also returns each row's bin key (None if a value is
    missing), for a permutation null stratified by bin."""
    def keys(values, classes):
        out = []
        for i, cls in enumerate(classes):
            v = [vals[i] for vals in values]
            out.append(
                tuple(int(np.floor(x / b)) for x, b in zip(v, bins)) + (cls,)
                if all(np.isfinite(v))
                else None
            )
        return out

    kt = keys([np.asarray(v, float) for v in target_values], list(target_class))
    ko = keys([np.asarray(v, float) for v in other_values], list(other_class))
    nt = pd.Series([k for k in kt if k is not None]).value_counts().to_dict()
    no = pd.Series([k for k in ko if k is not None]).value_counts().to_dict()
    wt = np.array([1.0 if k is not None and k in no else 0.0 for k in kt])
    wo = np.array([nt[k] / no[k] if k is not None and k in nt else 0.0 for k in ko])
    if return_keys:
        return wt, wo, kt, ko
    return wt, wo


def weighted_quantile(values, weights, q):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    ok = np.isfinite(values) & (weights > 0)
    if not ok.any():
        return np.nan
    order = np.argsort(values[ok])
    v, w = values[ok][order], weights[ok][order]
    cdf = np.cumsum(w) / w.sum()
    return float(v[min(np.searchsorted(cdf, q), len(v) - 1)])


def prepare(df, lum, core):
    df = df.merge(lum[["source", "name", "log_L_ph"]], on=["source", "name"], how="left")
    df = df.merge(core, on=["source", "name"], how="left")
    df["log_c"] = np.log10(df["c40_250"].where(df["c40_250"] > 0))
    return df


def null_columns(x, a, b, wa, wb, n_perm, strata=None):
    rows = np.r_[a["row"], b["row"]]
    labels = np.r_[np.ones(len(a)), np.zeros(len(b))]
    groups = np.r_[a["group"], b["group"]]
    mean, lo, hi = ae.null_auc(x[rows], labels, groups, weights=np.r_[wa, wb], n_perm=n_perm, strata=strata)
    return {"null_mean_L_c": mean, "null_lo_L_c": lo, "null_hi_L_c": hi}


def analyse(runs, lum, core, l_bin, c_bin, n_perm=0, null_config="harmonized_physical"):
    rows, dist = [], []
    for df, x, name in runs:
        df = prepare(df, lum, core)
        for z in ae.mock_redshifts(df):
            idx = ae.matched(df, z)
            sub = df.iloc[idx].copy()
            sub["row"] = idx
            lemur = sub[sub["source"] == "LEMUR"]
            mocks = sub[sub["source"] != "LEMUR"]
            exposures = sorted(mocks["exposure_ks"].unique())
            lemur_class = [mm.nearest_exposure(e, exposures) for e in lemur["exposure_ks"]]
            for sim in ["TNG300-1", "TNG-Cluster"]:
                s = mocks[mocks["source"] == sim]
                wl, ws, kl, ks = reweight_nd([lemur["log_L_ph"]], lemur_class, [s["log_L_ph"]], s["exposure_ks"], [l_bin], return_keys=True)
                wl2, ws2, kl2, ks2 = reweight_nd(
                    [lemur["log_L_ph"], lemur["log_c"]], lemur_class,
                    [s["log_L_ph"], s["log_c"]], s["exposure_ks"], [l_bin, c_bin], return_keys=True,
                )
                rows.append(
                    {
                        "config": name, "redshift": z, "pair": f"LEMUR vs {sim}",
                        **mm._ci_columns("auc_L", mm._weighted_auc_ci(x, lemur, s, wl, ws, strata=list(kl) + list(ks))),
                        **mm._ci_columns("auc_L_c", mm._weighted_auc_ci(x, lemur, s, wl2, ws2, strata=list(kl2) + list(ks2))),
                        "n_lemur_L": int(wl.sum()), "n_lemur_L_c": int(wl2.sum()),
                        "n_eff_mock_L": round(mm.n_eff(ws), 1), "n_eff_mock_L_c": round(mm.n_eff(ws2), 1),
                        **(null_columns(x, lemur, s, wl2, ws2, n_perm, list(kl2) + list(ks2)) if n_perm and name == null_config else {}),
                    }
                )
                if name == runs[0][2]:
                    dist.append(
                        {
                            "redshift": z, "sim": sim,
                            "lemur_median_c": weighted_quantile(lemur["c40_250"], wl, 0.5),
                            "mock_median_c": weighted_quantile(s["c40_250"], ws, 0.5),
                            "lemur_c_p75": weighted_quantile(lemur["c40_250"], wl, 0.75),
                            "mock_c_p75": weighted_quantile(s["c40_250"], ws, 0.75),
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(dist)


# ---------------------------------------------------------------- figures


def validation_figure(df, out):
    import matplotlib.pyplot as plt
    from scipy.stats import spearmanr

    labels = pd.read_csv(ROOT / "configs" / "halos" / "tng_cluster.csv")
    cl = df[df["source"] == "TNG-Cluster"].merge(labels, on="halo_id")
    zs = sorted(cl["redshift"].unique())
    fig, axes = plt.subplots(1, len(zs), figsize=(4.2 * len(zs), 3.6), squeeze=False, sharey=True)
    for ax, z in zip(axes[0], zs):
        s = cl[(cl["redshift"] == z) & (cl["exposure_ks"] == 100)]
        per_halo = s.groupby("halo_id").agg(c=("c40_250", "median"), t=("central_cooling_time_gyr_z0", "first"))
        rho = spearmanr(np.log10(per_halo["t"]), per_halo["c"], nan_policy="omit")[0]
        ax.scatter(per_halo["t"], per_halo["c"], s=8, c="tab:red", alpha=0.6)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"TNG-Cluster, z = {z:.2f}, 100 ks: Spearman {rho:.2f}", fontsize=9)
        ax.set_xlabel("central cooling time at z = 0 (Gyr)")
    axes[0, 0].set_ylabel(r"$c = F(<40)/F(<250\,$kpc)")
    fig.tight_layout()
    save_figure(fig, out / "core_validation.png")
    plt.close(fig)


def distribution_figure(df, out, l_bin):
    import matplotlib.pyplot as plt

    zs = ae.mock_redshifts(df)
    fig, axes = plt.subplots(1, len(zs), figsize=(4.4 * len(zs), 3.6), squeeze=False, sharey=True)
    bins = np.linspace(-2.2, 0, 34)
    for ax, z in zip(axes[0], zs):
        sub = df.iloc[ae.matched(df, z)]
        lemur = sub[sub["source"] == "LEMUR"]
        exposures = sorted(sub.loc[sub["source"] != "LEMUR", "exposure_ks"].unique())
        lemur_class = [mm.nearest_exposure(e, exposures) for e in lemur["exposure_ks"]]
        for sim in ["TNG300-1", "TNG-Cluster"]:
            s = sub[sub["source"] == sim]
            wl, ws = reweight_nd([lemur["log_L_ph"]], lemur_class, [s["log_L_ph"]], s["exposure_ks"], [l_bin])
            ax.hist(s["log_c"], bins, weights=ws, density=True, histtype="step", color=COLORS[sim], label=f"{sim}, L-matched")
        ax.hist(lemur["log_c"], bins, density=True, histtype="step", color="k", lw=1.5, label=f"LEMUR ({lemur['log_c'].notna().sum()})")
        ax.set_title(f"z = {z:.2f}", fontsize=9)
        ax.set_xlabel(r"log $c$ = log F(<40)/F(<250 kpc)")
        ax.legend(fontsize=7)
    fig.tight_layout()
    save_figure(fig, out / "core_distributions.png")
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
            for shift, key, color, label in [(-0.2, "auc_L", "tab:green", "matched L, exposure"), (0.2, "auc_L_c", "tab:purple", "+ concentration")]:
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
    save_figure(fig, out / "core_auc.png")
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default_runs = [str(p) for p in sorted((ROOT / "outputs" / "embeddings").glob("*")) if (p / "run.json").exists()]
    parser.add_argument("--runs", nargs="*", default=default_runs)
    parser.add_argument("--config", default=str(ROOT / "configs" / "harmonized_morphology.yaml"))
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "core"))
    parser.add_argument("--l-bin", type=float, default=0.2, help="log L bin (dex)")
    parser.add_argument("--c-bin", type=float, default=0.15, help="log c bin (dex)")
    parser.add_argument(
        "--luminosity-cache", default=str(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    )
    parser.add_argument("--no-signal-cut", action="store_true")
    parser.add_argument("--null", type=int, default=0, help="Label permutations for the (L, c)-matched null")
    parser.add_argument("--null-config", default="harmonized_physical", help="Run (config name) that gets the null")
    parser.add_argument("--snr-min", type=float, default=10.0)
    parser.add_argument("--ps-max", type=float, default=0.5)
    parser.add_argument("--probe", choices=["linear", "mlp"], default="linear",
                        help="Domain classifier; a non-default probe writes to <out>_<probe>")
    args = parser.parse_args(argv)
    ae.PROBE = args.probe
    out = Path(args.out + ("" if args.probe == "linear" else f"_{args.probe}"))
    out.mkdir(parents=True, exist_ok=True)
    core = measure(args.config, ROOT / "outputs" / "figures" / "core" / "core.csv")
    lum = mm.luminosities(args.config, args.luminosity_cache)
    cut = None
    if not args.no_signal_cut:
        cut = (pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv"), args.snr_min, args.ps_max)
    runs = [ae.load_run(r, cut) for r in args.runs]
    first = prepare(runs[0][0], lum, core)
    validation_figure(first, out)
    distribution_figure(first, out, args.l_bin)
    table, dist = analyse(runs, lum, core, args.l_bin, args.c_bin, args.null, args.null_config)
    table.to_csv(out / "core_auc.csv", index=False)
    dist.to_csv(out / "core_medians.csv", index=False)
    auc_figure(table, out)
    print(dist.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"Figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
