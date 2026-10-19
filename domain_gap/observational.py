"""Do observing conditions leave a mark on the embeddings?

    python -m domain_gap.observational [--null 50] [--out outputs/figures/observational]

The mocks are single ACIS-I aimpoint pointings at 20 or 100 ks; LEMUR mixes
ACIS-I and ACIS-S, single pointings and multi-ObsID mosaics, and exposures from
a few to hundreds of ks. Three tests, per preprocessing config:

1. Exposure in the mocks: domain AUC of 20 ks vs 100 ks images (both
   simulations, grouped by halo so no halo is in training and testing), and
   the cosine distance between the embeddings of the same halo and projection
   at 20 and 100 ks, against the distance between projections of one halo
   (100 ks) and between different halos of similar M500 (within 0.05 dex).
2. Within LEMUR: AUC between subsets split by an observing property
   (ACIS-S data or not, more than one ObsID or not, exposure below or above
   the median), with the second subset reweighted to the first in
   (log L, log c, z) and, except for the exposure split, log exposure.
3. LEMUR subsets against the mocks (both simulations pooled), reweighted to
   each subset's (log L, log c, exposure) at each mock redshift and pooled
   over redshift. If an observing property mattered, its subset would separate
   from the mocks more than the rest of LEMUR does.

Tests 2 and 3 use the signal cut and report a permutation null (``--null``).
Writes observational.csv, exposure_pairs.csv and observational.png.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import analyze_embeddings as ae
from . import core as core_mod
from . import mass_match as mm

ROOT = Path(__file__).resolve().parents[1]


def auc_with_null(x, a_rows, b_rows, wa, wb, groups_a, groups_b, n_perm):
    rows = np.r_[a_rows, b_rows]
    labels = np.r_[np.ones(len(a_rows)), np.zeros(len(b_rows))]
    groups = np.r_[groups_a, groups_b]
    weights = np.r_[wa, wb]
    value, lo, hi = ae.domain_auc_ci(x[rows], labels, groups, weights=weights)
    out = {"auc": value, "auc_lo": lo, "auc_hi": hi, "n_a": int((wa > 0).sum()), "n_eff_b": round(mm.n_eff(wb), 1)}
    if n_perm:
        mean, nlo, nhi = ae.null_auc(x[rows], labels, groups, weights=weights, n_perm=n_perm)
        out.update(null_mean=mean, null_lo=nlo, null_hi=nhi)
    return out


# ---------------------------------------------------------------- test 1


def exposure_tests(df, x, name):
    mocks = df[df["source"] != "LEMUR"].copy()
    mocks["row"] = np.where(df["source"] != "LEMUR")[0]
    rows, pairs = [], []
    for z in sorted(mocks["redshift"].unique()):
        m = mocks[mocks["redshift"] == z]
        deep, shallow = m[m["exposure_ks"] == 100], m[m["exposure_ks"] == 20]
        value, lo, hi = mm._weighted_auc_ci(x, shallow, deep, np.ones(len(shallow)), np.ones(len(deep)))
        rows.append({"config": name, "test": "mocks: 20 vs 100 ks", "redshift": z, "auc": value, "auc_lo": lo, "auc_hi": hi,
                     "n_a": len(shallow), "n_eff_b": float(len(deep))})
        # Paired distances.
        key = ["source", "halo_id", "projection"]
        both = shallow.merge(deep, on=key, suffixes=("_20", "_100"))
        d_exp = 1 - np.sum(x[both["row_20"]] * x[both["row_100"]], axis=1)
        d_proj = []
        for _, h in deep.groupby(["source", "halo_id"]):
            r = h["row"].to_numpy()
            for i in range(len(r)):
                for j in range(i + 1, len(r)):
                    d_proj.append(1 - float(x[r[i]] @ x[r[j]]))
        logm = np.log10(deep["M500c_Msun"].to_numpy())
        rng = np.random.default_rng(0)
        d_halo = []
        drow, dhalo = deep["row"].to_numpy(), deep["halo_id"].to_numpy()
        for i in rng.choice(len(deep), min(len(deep), 600), replace=False):
            close = np.where((np.abs(logm - logm[i]) < 0.05) & (dhalo != dhalo[i]))[0]
            if len(close):
                d_halo.append(1 - float(x[drow[i]] @ x[drow[rng.choice(close)]]))
        pairs.append({"config": name, "redshift": z,
                      "same_halo_20_vs_100ks": float(np.median(d_exp)),
                      "same_halo_other_projection": float(np.median(d_proj)),
                      "other_halo_same_mass": float(np.median(d_halo))})
    return rows, pairs


# ---------------------------------------------------------------- tests 2 and 3


def lemur_properties(lemur):
    return {
        "has ACIS-S data": lemur["n_acis_s"].fillna(0) > 0,
        "more than one ObsID": lemur["n_obsids"].fillna(1) > 1,
        "exposure above median": lemur["exposure_ks"] > lemur["exposure_ks"].median(),
    }


def internal_tests(df, x, name, n_perm):
    lemur = df[(df["source"] == "LEMUR") & df["log_L_ph"].notna() & df["log_c"].notna()].copy()
    lemur["row"] = np.where((df["source"] == "LEMUR") & df["log_L_ph"].notna() & df["log_c"].notna())[0]
    lemur["log_exp"] = np.log10(lemur["exposure_ks"])
    rows = []
    for prop, mask in lemur_properties(lemur).items():
        a, b = lemur[mask.to_numpy()], lemur[~mask.to_numpy()]
        cols = ["log_L_ph", "log_c", "redshift"] + ([] if prop.startswith("exposure") else ["log_exp"])
        # Coarse bins: four matching variables on ~700 clusters leave few per bin.
        bins = [0.3, 0.2, 0.1] + ([] if prop.startswith("exposure") else [0.5])
        wa, wb = core_mod.reweight_nd([a[c] for c in cols], ["-"] * len(a), [b[c] for c in cols], ["-"] * len(b), bins)
        rows.append({"config": name, "test": f"LEMUR: {prop} vs not", "redshift": np.nan,
                     **auc_with_null(x, a["row"].to_numpy(), b["row"].to_numpy(), wa, wb, a["group"], b["group"], n_perm)})
    return rows


def versus_mocks(df, x, name, n_perm):
    df = df.copy()
    df["row"] = np.arange(len(df))
    lemur_all = df[df["source"] == "LEMUR"]
    subsets = {"all LEMUR": np.ones(len(lemur_all), bool)}
    for prop, mask in lemur_properties(lemur_all).items():
        subsets[prop] = mask.to_numpy()
        subsets[f"not {prop}"] = ~mask.to_numpy()
    rows = []
    for label, mask in subsets.items():
        lemur = lemur_all[mask]
        a_rows, b_rows, wa_all, wb_all, ga, gb = [], [], [], [], [], []
        for z in ae.mock_redshifts(df):
            near = lemur[(lemur["redshift"] - z).abs() < ae.Z_WIDTH + 1e-9]
            mocks = df[(df["source"] != "LEMUR") & (df["redshift"] == z)]
            if len(near) == 0:
                continue
            exposures = sorted(mocks["exposure_ks"].unique())
            cls = [mm.nearest_exposure(e, exposures) for e in near["exposure_ks"]]
            wa, wb = core_mod.reweight_nd([near["log_L_ph"], near["log_c"]], cls, [mocks["log_L_ph"], mocks["log_c"]], mocks["exposure_ks"], [0.2, 0.15])
            a_rows.append(near["row"].to_numpy()); b_rows.append(mocks["row"].to_numpy())
            wa_all.append(wa); wb_all.append(wb); ga.append(near["group"].to_numpy()); gb.append(mocks["group"].to_numpy())
        if not a_rows:
            continue
        # A mock image can appear at one redshift only, so concatenating keeps rows unique.
        rows.append({"config": name, "test": f"vs mocks: {label}", "redshift": np.nan,
                     **auc_with_null(x, np.concatenate(a_rows), np.concatenate(b_rows), np.concatenate(wa_all),
                                     np.concatenate(wb_all), np.concatenate(ga), np.concatenate(gb), n_perm)})
    return rows


# ---------------------------------------------------------------- figure


def figure(table, pairs, out):
    import matplotlib.pyplot as plt

    configs = list(dict.fromkeys(table["config"]))
    tests = [t for t in dict.fromkeys(table["test"]) if not t.startswith("mocks:")]
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.32 * len(tests) * len(configs) + 2), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axes[0]
    y = 0
    ticks, labels = [], []
    colors = {"baseline": "tab:blue", "harmonized_morphology": "tab:orange", "harmonized_physical": "tab:green"}
    for test in tests:
        for config in configs:
            r = table[(table["test"] == test) & (table["config"] == config)]
            if not len(r):
                continue
            r = r.iloc[0]
            ax.errorbar(r["auc"], y, xerr=[[r["auc"] - r["auc_lo"]], [r["auc_hi"] - r["auc"]]], fmt="o", color=colors.get(config, "k"), ms=4)
            if "null_lo" in r and np.isfinite(r.get("null_lo", np.nan)):
                ax.plot([r["null_lo"], r["null_hi"]], [y, y], color="0.75", lw=6, zorder=0, solid_capstyle="butt")
            y += 1
        ticks.append(y - len(configs) / 2 - 0.5)
        labels.append(test)
        y += 0.6
    ax.axvline(0.5, color="gray", ls="--", lw=0.8)
    ax.set_yticks(ticks, labels, fontsize=7)
    ax.set_xlabel("domain AUC (grey band: permutation null, 68%)")
    ax.invert_yaxis()
    for config, color in colors.items():
        ax.plot([], [], "o", color=color, label=config)
    ax.legend(fontsize=7, loc="lower right")
    ax2 = axes[1]
    p = pairs.groupby("config")[["same_halo_20_vs_100ks", "same_halo_other_projection", "other_halo_same_mass"]].median()
    p.plot.bar(ax=ax2, rot=20, fontsize=7)
    ax2.set_ylabel("median cosine distance")
    ax2.set_title("mocks: what moves an embedding", fontsize=9)
    ax2.legend(fontsize=6.5)
    fig.tight_layout()
    fig.savefig(out / "observational.png", dpi=120)
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default_runs = [str(p) for p in sorted((ROOT / "outputs" / "embeddings").glob("*")) if (p / "run.json").exists()]
    parser.add_argument("--runs", nargs="*", default=default_runs)
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "observational"))
    parser.add_argument("--null", type=int, default=50, help="Permutations for tests 2-3 (physical config)")
    parser.add_argument("--null-config", default="harmonized_physical")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lum = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    cut = (pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv"), 10.0, 0.5)
    rows, pairs = [], []
    for run in args.runs:
        df_all, x_all, name = ae.load_run(run)
        r, p = exposure_tests(df_all, x_all, name)
        rows += r
        pairs += p
        df, x, name = ae.load_run(run, cut)
        df = core_mod.prepare(df, lum, core)
        n_perm = args.null if name == args.null_config else 0
        rows += internal_tests(df, x, name, n_perm)
        rows += versus_mocks(df, x, name, n_perm)
        print(f"{name}: done", flush=True)
    table, pairs = pd.DataFrame(rows), pd.DataFrame(pairs)
    table.to_csv(out / "observational.csv", index=False)
    pairs.to_csv(out / "exposure_pairs.csv", index=False)
    figure(table, pairs, out)
    show = ["config", "test", "redshift", "auc", "auc_lo", "auc_hi", "n_a", "n_eff_b"] + [c for c in ["null_mean", "null_lo", "null_hi"] if c in table]
    print(table[show].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(pairs.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"Figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
