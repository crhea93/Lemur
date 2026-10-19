"""What makes LEMUR separable from the mocks in a given embedding space?

    python -m domain_gap.drivers --run outputs/embeddings/simclr_mocks [--out ...]

At each mock redshift, LEMUR is compared with the mocks reweighted to its
(log L, log c, exposure), as in domain_gap.core (signal cut applied). Then:

1. scores: every image's out-of-fold classifier score (higher = more
   LEMUR-like). For LEMUR, its Spearman correlation with observing and
   image properties: point-source fraction, S/N, coverage, exposure, ACIS-S
   data, number of ObsIDs, pixel binning, luminosity and concentration
   (drivers_correlations.csv).
2. extra matching: the AUC when candidate properties are added to the
   reweighting (point-source fraction, coverage, S/N, and S/N with
   point-source fraction). If adding one moves the AUC to the null, that
   property carries the gap (drivers_matching.csv).
3. drivers_gallery.png: the model inputs of the most and least LEMUR-like
   LEMUR clusters and of the most LEMUR-like mocks.
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
PREPROCESSED = Path("/run/media/crhea/ef10789c-0ada-41e4-8d3f-8f17dbcc0558/_domain_gap/preprocessed")
PROPERTIES = {
    "ps_fraction": "point-source fraction",
    "log_snr": "log S/N (250 kpc)",
    "coverage_mean": "field coverage",
    "coverage_core": "core coverage",
    "log_exposure": "log exposure",
    "acis_s": "has ACIS-S data",
    "log_n_obsids": "log number of ObsIDs",
    "image_pixel_arcsec": "image pixel (binning)",
    "log_L_ph": "log L (250 kpc)",
    "log_c": "log concentration",
}
EXTRA = {"ps_fraction": 0.1, "coverage_mean": 0.02, "log_snr": 0.3}
EXTRA_SETS = [(), ("ps_fraction",), ("coverage_mean",), ("log_snr",), ("log_snr", "ps_fraction")]


def prepare(run_dir):
    lum = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    sig = pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv")
    df, x, name = ae.load_run(run_dir, (sig, 10.0, 0.5))
    df = core_mod.prepare(df, lum, core)
    df = df.merge(sig[["source", "name", "snr", "ps_fraction"]], on=["source", "name"], how="left")
    df["log_snr"] = np.log10(df["snr"].clip(lower=1))
    df["log_exposure"] = np.log10(df["exposure_ks"])
    df["acis_s"] = (df["n_acis_s"].fillna(0) > 0).astype(float)
    df["log_n_obsids"] = np.log10(df["n_obsids"].fillna(1).clip(lower=1))
    df["row"] = np.arange(len(df))
    return df, x, name


def matched_sets(df, sim, extra=()):
    """Per mock redshift: (lemur rows, mock rows, LEMUR weights, mock weights)."""
    out = []
    for z in ae.mock_redshifts(df):
        lemur = df[(df["source"] == "LEMUR") & ((df["redshift"] - z).abs() < ae.Z_WIDTH + 1e-9)]
        mocks = df[(df["source"] == sim) & (df["redshift"] == z)]
        exposures = sorted(mocks["exposure_ks"].unique())
        cls = [mm.nearest_exposure(e, exposures) for e in lemur["exposure_ks"]]
        cols, bins = ["log_L_ph", "log_c"], [0.2, 0.15]
        cols, bins = cols + list(extra), bins + [EXTRA[e] for e in extra]
        wl, wm = core_mod.reweight_nd([lemur[c] for c in cols], cls, [mocks[c] for c in cols], mocks["exposure_ks"], bins)
        out.append((z, lemur, mocks, wl, wm))
    return out


def scores_and_auc(x, lemur, mocks, wl, wm):
    rows = np.r_[lemur["row"], mocks["row"]]
    labels = np.r_[np.ones(len(lemur)), np.zeros(len(mocks))]
    groups = np.r_[lemur["group"], mocks["group"]]
    weights = np.r_[wl, wm]
    keep = weights > 0
    result = ae.domain_auc(x[rows], labels, groups, weights=weights, return_scores=True)
    if not isinstance(result, tuple):
        return np.nan, None
    value, scores, lab, grp, w = result
    kept_rows = rows[keep]
    return value, pd.DataFrame({"row": kept_rows, "score": scores, "label": lab})


def correlations(df, x):
    from scipy.stats import spearmanr

    rows, all_scores = [], []
    for sim in ["TNG300-1", "TNG-Cluster"]:
        for z, lemur, mocks, wl, wm in matched_sets(df, sim):
            value, s = scores_and_auc(x, lemur, mocks, wl, wm)
            if s is None:
                continue
            # Standardize within each comparison so scores can be pooled.
            s["score"] = (s["score"] - s["score"].mean()) / (s["score"].std() + 1e-12)
            s["sim"], s["redshift"], s["auc"] = sim, z, value
            all_scores.append(s)
    scores = pd.concat(all_scores, ignore_index=True)
    lemur_scores = scores[scores["label"] == 1].groupby("row")["score"].mean()
    lemur = df.loc[lemur_scores.index].assign(score=lemur_scores.to_numpy())
    for col, label in PROPERTIES.items():
        ok = lemur[[col, "score"]].dropna()
        rho, p = spearmanr(ok[col], ok["score"]) if len(ok) > 5 else (np.nan, np.nan)
        rows.append({"property": label, "column": col, "spearman_rho": rho, "p_value": p, "n": len(ok)})
    return pd.DataFrame(rows).sort_values("spearman_rho", key=np.abs, ascending=False), scores


def extra_matching(df, x):
    rows = []
    for extra in EXTRA_SETS:
        for sim in ["TNG300-1", "TNG-Cluster"]:
            for z, lemur, mocks, wl, wm in matched_sets(df, sim, extra):
                value, lo, hi = mm._weighted_auc_ci(x, lemur, mocks, wl, wm)
                rows.append({"matched_on": ", ".join(["L, c, exposure", *extra]), "sim": sim, "redshift": z,
                             "auc": value, "auc_lo": lo, "auc_hi": hi, "n_lemur": int((wl > 0).sum()), "n_eff_mock": round(mm.n_eff(wm), 1)})
    return pd.DataFrame(rows)


def gallery(df, scores, out, n=8):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    run = PREPROCESSED / "harmonized_physical"
    inputs = {s: np.load(run / f"inputs_{s}.npy", mmap_mode="r") for s in ["LEMUR", "TNG300-1", "TNG-Cluster"]}
    mean_scores = scores.groupby("row").agg(score=("score", "mean"), label=("label", "first"))
    lemur = mean_scores[mean_scores["label"] == 1].sort_values("score")
    mocks = mean_scores[mean_scores["label"] == 0].sort_values("score")
    panels = [("most LEMUR-like LEMUR", lemur.index[::-1][:n]), ("least LEMUR-like LEMUR", lemur.index[:n]),
              ("most LEMUR-like mocks", mocks.index[::-1][:n])]
    fig, axes = plt.subplots(len(panels), n, figsize=(1.7 * n, 1.9 * len(panels)))
    for r, (title, idx) in enumerate(panels):
        for c, row in enumerate(idx):
            info = df.loc[row]
            ax = axes[r, c]
            ax.imshow(inputs[info["source"]][int(info["index"])], origin="lower", cmap="magma", vmin=0, vmax=1)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{str(info['name'])[:16]}\nps={info['ps_fraction']:.2f} z={info['redshift']:.2f}", fontsize=5.5)
        axes[r, 0].set_ylabel(title, fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "drivers_gallery.png", dpi=130)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", default=str(ROOT / "outputs" / "embeddings" / "simclr_mocks"))
    parser.add_argument("--out")
    parser.add_argument("--probe", choices=["linear", "mlp"], default="linear")
    args = parser.parse_args(argv)
    ae.PROBE = args.probe
    df, x, name = prepare(args.run)
    out = Path(args.out or ROOT / "outputs" / "figures" / f"drivers_{name}")
    out.mkdir(parents=True, exist_ok=True)
    corr, scores = correlations(df, x)
    corr.to_csv(out / "drivers_correlations.csv", index=False)
    print(f"{name}: correlation of LEMUR's out-of-fold score with each property")
    print(corr.to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    gallery(df, scores, out)
    extra = extra_matching(df, x)
    extra.to_csv(out / "drivers_matching.csv", index=False)
    print(extra.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"Outputs in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
