"""The domain gap of the original setup, and how each step of this project changes it.

    ~/miniconda3/envs/lemur-astroclip/bin/python -m domain_gap.original_gap
        [--student ~/friend-mac-recovery/MSC_LATEST/May] [--out outputs/figures/original]

The original experiment compared LEMUR's AstroCLIP embeddings (LEMUR's own
preprocessing, which configs/baseline.yaml reproduces exactly) with the
student's mock embeddings: z = 0.05, 100 ks, 0.5-2 keV images binned 4x4,
min-max normalized, cropped to 252 px, saved as PNG (greyscale for TNG300,
viridis for TNG-Cluster) and embedded at 252 px (docs/tng_mock_provenance.md).
Their final embeddings survive in val_data300.pt (714 images) and
val_datacluster.pt (993 images), with halo IDs.

All comparisons are at z = 0.05 (LEMUR within +-0.025) and, for the mocks,
100 ks, like the student's. Steps:

  0. original: student mocks vs LEMUR's own embeddings;
  1. regenerated mocks, LEMUR's preprocessing for both (baseline);
  2. harmonized morphology; 3. harmonized physical;
and the simulation-vs-simulation AUC of each, with TNG300 also reweighted to
TNG-Cluster's true M500 (masses of the same halos from the regenerated
manifest). Steps with matching on luminosity and concentration are in
domain_gap.core (outputs/figures/core).

Writes original_gap.csv and original_pca.png.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import analyze_embeddings as ae
from . import mass_match as mm

ROOT = Path(__file__).resolve().parents[1]
STUDENT = Path.home() / "friend-mac-recovery" / "MSC_LATEST" / "May"
Z_MOCK = 0.05
EXPOSURE_KS = 100.0


def load_student(folder):
    """Student embeddings as (DataFrame of source/halo/projection, L2-normalized vectors)."""
    import torch

    frames, vectors = [], []
    for source, name in [("TNG300-1", "val_data300.pt"), ("TNG-Cluster", "val_datacluster.pt")]:
        data = torch.load(Path(folder) / name, weights_only=True, map_location="cpu")
        emb = np.asarray(data["embeddings"], dtype=np.float32)
        ids = [int(i) for i in data["cluster_ids"]]
        proj = [re.match(r"([xyz])_proj", f).group(1) for f in data["filenames"]]
        frames.append(pd.DataFrame({"source": source, "halo_id": ids, "projection": proj, "filename": list(data["filenames"])}))
        vectors.append(emb)
    df = pd.concat(frames, ignore_index=True)
    x = np.concatenate(vectors)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    df["group"] = df["source"] + ":" + df["halo_id"].astype(str)
    return df, x


def halo_masses(manifest_path):
    m = pd.read_parquet(manifest_path)
    m = m[m["source"] != "LEMUR"].dropna(subset=["halo_id"])
    return m.groupby(["source", "halo_id"])["M500c_Msun"].first().reset_index().astype({"halo_id": int})


def aucs(x, df):
    """AUCs of the three pairs, plus TNG-Cluster vs TNG300 reweighted to equal true M500."""
    rows = {}
    for a, b in [("LEMUR", "TNG300-1"), ("LEMUR", "TNG-Cluster"), ("TNG-Cluster", "TNG300-1")]:
        sa, sb = df[df["source"] == a], df[df["source"] == b]
        rows[f"{a} vs {b}"] = mm._weighted_auc(x, sa.assign(row=sa.index), sb.assign(row=sb.index), np.ones(len(sa)), np.ones(len(sb)))
    ca, tb = df[df["source"] == "TNG-Cluster"], df[df["source"] == "TNG300-1"]
    wc, wt = mm.reweight(np.log10(ca["M500c_Msun"]), ["-"] * len(ca), np.log10(tb["M500c_Msun"]), ["-"] * len(tb), 0.1)
    rows["TNG-Cluster vs TNG300-1 (equal M500)"] = mm._weighted_auc(x, ca.assign(row=ca.index), tb.assign(row=tb.index), wc, wt)
    return rows


def step_original(student, masses, lemur_df, lemur_x):
    sdf, sx = student
    sdf = sdf.merge(masses, on=["source", "halo_id"], how="left")
    df = pd.concat([lemur_df.assign(row=np.arange(len(lemur_df))), sdf], ignore_index=True)
    x = np.concatenate([lemur_x, sx])
    return aucs(x, df), df, x


def step_run(run_dir, signal_cut=None):
    df, x, name = ae.load_run(run_dir, signal_cut)
    keep = ((df["source"] == "LEMUR") & ((df["redshift"] - Z_MOCK).abs() < ae.Z_WIDTH + 1e-9)) | (
        (df["source"] != "LEMUR") & (df["redshift"] == Z_MOCK) & (df["exposure_ks"] == EXPOSURE_KS)
    )
    idx = np.where(keep)[0]
    sub = df.iloc[idx].reset_index(drop=True)
    return aucs(x[idx], sub), sub, x[idx], name


def pca_figure(panels, out):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(panels), figsize=(4.4 * len(panels), 4.2), squeeze=False)
    rng = np.random.default_rng(0)
    for ax, (title, df, x) in zip(axes[0], panels):
        n = min(df["source"].value_counts())
        fit = np.concatenate([rng.choice(np.where(df["source"].to_numpy() == s)[0], n, replace=False) for s in df["source"].unique()])
        mean = x[fit].mean(axis=0)
        _, _, vt = np.linalg.svd(x[fit] - mean, full_matrices=False)
        proj = (x - mean) @ vt[:2].T
        for source in ["TNG300-1", "TNG-Cluster", "LEMUR"]:
            m = df["source"].to_numpy() == source
            ax.scatter(proj[m, 0], proj[m, 1], s=6 if source != "LEMUR" else 14, c=ae.COLORS[source],
                       alpha=0.35 if source != "LEMUR" else 0.9, linewidths=0, label=f"{source} ({m.sum()})")
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.legend(fontsize=7, markerscale=2)
    fig.tight_layout()
    fig.savefig(out / "original_pca.png", dpi=120)
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--student", default=str(STUDENT))
    parser.add_argument("--embeddings", default=str(ROOT / "outputs" / "embeddings"))
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "original"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    emb = Path(args.embeddings)

    rows, panels = [], []
    # Steps 1-3 (and LEMUR's original embeddings = baseline LEMUR at z ~ 0.05).
    runs = {}
    for config in ["baseline", "harmonized_morphology", "harmonized_physical"]:
        result, df, x, name = step_run(emb / config)
        runs[config] = (result, df, x)
    base_df, base_x = runs["baseline"][1], runs["baseline"][2]
    lemur_mask = (base_df["source"] == "LEMUR").to_numpy()
    lemur_df = base_df[lemur_mask][["source", "name", "group"]].reset_index(drop=True)
    masses = halo_masses(emb / "baseline" / "manifest.parquet")
    result, df0, x0 = step_original(load_student(args.student), masses, lemur_df, base_x[lemur_mask])
    rows.append({"step": "0 original (student mocks, their PNG pipeline)", **result})
    panels.append(("0: original setup", df0, x0))
    labels = {"baseline": "1 regenerated mocks, LEMUR preprocessing", "harmonized_morphology": "2 harmonized morphology", "harmonized_physical": "3 harmonized physical"}
    for config, (result, df, x) in runs.items():
        rows.append({"step": labels[config], **result})
        panels.append((labels[config].split(" ", 1)[0] + ": " + labels[config].split(" ", 1)[1], df, x))
    table = pd.DataFrame(rows)
    table.to_csv(out / "original_gap.csv", index=False)
    pca_figure(panels, out)
    n = df0["source"].value_counts().to_dict()
    print(f"z = {Z_MOCK}, mocks {EXPOSURE_KS:g} ks; original sample sizes {n}")
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"Figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
