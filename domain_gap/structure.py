"""Small-scale structure in the central 150 kpc, and whether the embeddings see it.

    python -m domain_gap.structure measure      # metrics from the 150 kpc extraction (cached)
    python -m domain_gap.structure analyse      # embeddings vs metrics; LEMUR vs mocks

From the stage-1 surface brightness of configs/harmonized_core_physical.yaml
(150 kpc, ~1 kpc pixels; masked smoothing of 1.5 px), around the X-ray peak:

- centroid shift w: the standard deviation of the distance between the peak
  and the brightness centroid within apertures of 15, 25, ..., 75 kpc, over
  75 kpc (a dynamical-state indicator; cf. Mohr et al. 1993, Poole et al. 2006);
- residual RMS: the RMS of the smoothed image minus its azimuthal average
  profile (2 px annuli) within 75 kpc, over the mean surface brightness there
  (cavities, cold fronts, sloshing spirals; noise contributes too, which is
  why the comparisons below match S/N).

``analyse`` reports, for each embedding run (500 kpc and 150 kpc
configurations), the grouped cross-validated R^2 of ridge regressions of
log w and log residual RMS, both directly and after removing what log L,
log c and log S/N explain (structure beyond brightness, concentration and
noise). It also compares LEMUR with the mocks reweighted to its
(log L, log S/N, exposure) at each redshift: medians with bootstrap 68%
intervals.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import preprocess, spatial

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "structure"
CONFIG = ROOT / "configs" / "harmonized_core_physical.yaml"
APERTURES_KPC = (15, 25, 35, 45, 55, 65, 75)
R_MAX_KPC = 75.0


def metrics(sb, coverage, field_kpc):
    grid = sb.shape[0]
    mask = coverage >= 0.5
    img = spatial.masked_smooth(sb, mask, 1.5).astype(np.float64)
    yy, xx = np.indices(img.shape)
    c0 = (grid - 1) / 2
    r = np.hypot(xx - c0, yy - c0) * field_kpc / grid
    inside = mask & (r < R_MAX_KPC)
    if inside.sum() < 0.9 * (r < R_MAX_KPC).sum():
        return np.nan, np.nan
    shifts = []
    for ap in APERTURES_KPC:
        sel = mask & (r < ap)
        w = np.clip(img[sel], 0, None)
        if w.sum() <= 0:
            return np.nan, np.nan
        cx, cy = (xx[sel] * w).sum() / w.sum(), (yy[sel] * w).sum() / w.sum()
        shifts.append(np.hypot(cx - c0, cy - c0) * field_kpc / grid)
    centroid_shift = float(np.std(shifts) / R_MAX_KPC)
    edges = np.arange(0, R_MAX_KPC + 2 * field_kpc / grid, 2 * field_kpc / grid)
    which = np.digitize(r, edges) - 1
    profile = np.full(len(edges), np.nan)
    for k in range(len(edges) - 1):
        sel = inside & (which == k)
        if sel.any():
            profile[k] = img[sel].mean()
    model = profile[np.clip(which, 0, len(edges) - 1)]
    resid = img[inside] - model[inside]
    mean = img[inside].mean()
    residual_rms = float(np.sqrt(np.nanmean(resid**2)) / mean) if mean > 0 else np.nan
    return centroid_shift, residual_rms


def measure(args):
    cache = OUT / "structure.csv"
    if cache.exists() and not args.force:
        print(f"{cache} exists (use --force to remeasure)")
        return
    cfg = preprocess.load_config(CONFIG)
    base = Path(cfg.get("stage1_dir", preprocess.PREPROCESSED / "_stage1")) / preprocess.spatial_hash(cfg)
    rows = []
    for source_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for path in sorted(source_dir.glob("*.npz")):
            with np.load(path) as data:
                info = json.loads(str(data["info"]))
                if info.get("status") != "ok":
                    continue
                w, rms = metrics(data["sb"], data["coverage"], info["field_kpc"])
            rows.append({"source": info["source"], "name": info["name"], "centroid_shift": w, "residual_rms": rms})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(cache, index=False)
    print(f"Measured {len(rows)} images")


def load(run_dir=None):
    from . import analyze_embeddings as ae

    st = pd.read_csv(OUT / "structure.csv")
    lum = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    sig = pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv")
    if run_dir is None:
        run_dir = ROOT / "outputs" / "embeddings" / "harmonized_core_physical"
    df, x, name = ae.load_run(run_dir, (sig, 10.0, 0.5))
    df = df.merge(st, on=["source", "name"], how="left").merge(lum[["source", "name", "log_L_ph"]], on=["source", "name"], how="left")
    df = df.merge(core, on=["source", "name"], how="left").merge(sig[["source", "name", "snr"]], on=["source", "name"], how="left")
    df["log_w"] = np.log10(df["centroid_shift"].where(df["centroid_shift"] > 0))
    df["log_rms"] = np.log10(df["residual_rms"].where(df["residual_rms"] > 0))
    df["log_c"] = np.log10(df["c40_250"].where(df["c40_250"] > 0))
    df["log_snr"] = np.log10(df["snr"])
    return df, x, name


def residualize(y, covariates):
    """y minus its least-squares fit on the covariates (with intercept)."""
    a = np.column_stack([np.ones(len(y)), *covariates])
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    return y - a @ coef


def analyse(args):
    from .simclr import ridge_cv_r2

    rows = []
    for run in args.runs:
        df, x, name = load(ROOT / "outputs" / "embeddings" / run)
        ok = df[["log_w", "log_rms", "log_L_ph", "log_c", "log_snr"]].notna().all(axis=1).to_numpy()
        d, xs = df[ok], x[ok]
        cov = [d["log_L_ph"].to_numpy(), d["log_c"].to_numpy(), d["log_snr"].to_numpy()]
        row = {"run": name, "n": int(ok.sum())}
        for col in ["log_w", "log_rms"]:
            y = d[col].to_numpy()
            row[f"R2_{col}"] = ridge_cv_r2(xs, y, d["group"].to_numpy())
            row[f"R2_{col}_beyond_L_c_snr"] = ridge_cv_r2(xs, residualize(y, cov), d["group"].to_numpy())
        rows.append(row)
        print(row, flush=True)
    controls = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    controls.to_csv(OUT / "structure_r2.csv", index=False)
    print(controls.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    comparison = compare()
    comparison.to_csv(OUT / "structure_lemur_vs_mocks.csv", index=False)
    print(comparison.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    figure(comparison)


def weighted_median(v, w):
    v, w = np.asarray(v, float), np.asarray(w, float)
    ok = np.isfinite(v) & (w > 0)
    if not ok.any():
        return np.nan
    order = np.argsort(v[ok])
    cdf = np.cumsum(w[ok][order]) / w[ok].sum()
    return float(v[ok][order][np.searchsorted(cdf, 0.5)])


def compare(n_boot=1000, seed=0):
    from . import analyze_embeddings as ae
    from . import core as core_mod
    from . import mass_match as mm

    df, _, _ = load()
    rng = np.random.default_rng(seed)
    rows = []
    for z in ae.mock_redshifts(df):
        lemur = df[(df["source"] == "LEMUR") & ((df["redshift"] - z).abs() < ae.Z_WIDTH + 1e-9)].dropna(subset=["log_w", "log_rms", "log_snr"])
        mocks = df[(df["source"] != "LEMUR") & (df["redshift"] == z)].dropna(subset=["log_w", "log_rms", "log_snr"])
        exposures = sorted(mocks["exposure_ks"].unique())
        cls = [mm.nearest_exposure(e, exposures) for e in lemur["exposure_ks"]]
        wl, wm = core_mod.reweight_nd([lemur["log_L_ph"], lemur["log_snr"]], cls, [mocks["log_L_ph"], mocks["log_snr"]], mocks["exposure_ks"], [0.2, 0.3])
        lemur = lemur[wl > 0]
        groups = mocks.groupby("group").indices
        keys = list(groups)
        for col, label in [("centroid_shift", "centroid shift w"), ("residual_rms", "residual RMS")]:
            lv, mv = lemur[col].to_numpy(), mocks[col].to_numpy()
            ml, mmed = float(np.median(lv)), weighted_median(mv, wm)
            bl, bm = [], []
            for _ in range(n_boot):
                bl.append(np.median(lv[rng.integers(0, len(lv), len(lv))]))
                idx = np.concatenate([groups[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
                bm.append(weighted_median(mv[idx], wm[idx]))
            diff = np.array(bl) - np.array(bm)
            rows.append({"redshift": z, "metric": label, "n_lemur": len(lv), "lemur_median": ml,
                         "lemur_lo": np.percentile(bl, 16), "lemur_hi": np.percentile(bl, 84),
                         "mock_median": mmed, "mock_lo": np.nanpercentile(bm, 16), "mock_hi": np.nanpercentile(bm, 84),
                         "p_lemur_not_higher": float(np.mean(diff <= 0))})
    return pd.DataFrame(rows)


def figure(comparison):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics_ = list(dict.fromkeys(comparison["metric"]))
    fig, axes = plt.subplots(1, len(metrics_), figsize=(4.4 * len(metrics_), 3.4))
    for ax, metric in zip(np.atleast_1d(axes), metrics_):
        t = comparison[comparison["metric"] == metric]
        x = np.arange(len(t))
        for key, color, dx, label in [("lemur", "k", -0.08, "LEMUR"), ("mock", "tab:purple", 0.08, "mocks matched in L, S/N, exposure")]:
            v = t[f"{key}_median"].to_numpy()
            ax.errorbar(x + dx, v, yerr=[v - t[f"{key}_lo"], t[f"{key}_hi"] - v], fmt="o", color=color, capsize=2, label=label)
        ax.set_xticks(x, [f"z={z:g}" for z in t["redshift"]])
        ax.set_ylabel(f"median {metric}")
        ax.set_yscale("log")
    np.atleast_1d(axes)[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "structure_lemur_vs_mocks.png", dpi=130)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--force", action="store_true")
    a = sub.add_parser("analyse")
    a.add_argument("--runs", nargs="*", default=["harmonized_physical", "harmonized_morphology", "harmonized_core_physical", "harmonized_core_morphology"])
    args = parser.parse_args(argv)
    {"measure": measure, "analyse": analyse}[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
