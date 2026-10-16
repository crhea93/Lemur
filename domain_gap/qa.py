"""QA figures of a preprocessing run, LEMUR against the mocks at matched redshift.

    python -m domain_gap.qa --run <output_dir> [--out <dir>]

- examples.png: random usable model inputs per source, in redshift bins
  around the mock redshifts;
- pixels.png: distributions of covered input pixels and of field coverage;
- profiles.png (physical fields only): median surface-brightness profiles in
  kpc from the stage-1 extraction, before any normalization.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import manifest, preprocess

COLORS = {"LEMUR": "k", "TNG300-1": "tab:blue", "TNG-Cluster": "tab:red"}


def redshift_bins(df, width=0.025):
    """Mock redshifts, with LEMUR matched within +-width."""
    mocks = sorted(df.loc[df["source"] != "LEMUR", "redshift"].dropna().unique())
    return [(z, z - width, z + width) for z in mocks]


def in_bin(df, lo, hi):
    return df["usable"] & (df["redshift"] >= lo) & (df["redshift"] < hi)


def examples(df, run_dir, out, per_row=6, seed=0):
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(seed)
    sources = list(dict.fromkeys(df["source"]))
    bins = redshift_bins(df)
    rows = [(z, lo, hi, s) for z, lo, hi in bins for s in sources]
    if not rows:
        return
    fig, axes = plt.subplots(len(rows), per_row, figsize=(1.6 * per_row, 1.7 * len(rows)), squeeze=False)
    for r, (z, lo, hi, source) in enumerate(rows):
        sel = df[in_bin(df, lo, hi) & (df["source"] == source)]
        inputs = np.load(run_dir / f"inputs_{source}.npy", mmap_mode="r")
        picks = sel.iloc[rng.permutation(len(sel))[:per_row]] if len(sel) else sel
        for c in range(per_row):
            ax = axes[r, c]
            ax.set_xticks([])
            ax.set_yticks([])
            if c < len(picks):
                row = picks.iloc[c]
                ax.imshow(inputs[int(row["index"])], origin="lower", cmap="magma", vmin=0, vmax=1)
                ax.set_title(str(row["name"])[:18], fontsize=6)
        axes[r, 0].set_ylabel(f"{source}\nz={z:.2f} (n={len(sel)})", fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "examples.png", dpi=110)
    plt.close(fig)


def pixels(df, run_dir, out):
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    bins = np.linspace(0, 1, 51)
    for source in dict.fromkeys(df["source"]):
        sel = df[df["usable"] & (df["source"] == source)]
        if not len(sel):
            continue
        inputs = np.load(run_dir / f"inputs_{source}.npy", mmap_mode="r")
        masks = np.load(run_dir / f"masks_{source}.npy", mmap_mode="r")
        idx = sel["index"].astype(int).to_numpy()
        values = np.concatenate([inputs[i][masks[i] > 0] for i in idx[:2000]])
        a1.hist(values, bins, density=True, histtype="step", color=COLORS.get(source), label=f"{source} ({len(sel)})")
        ok = df[(df["source"] == source) & (df["status"] == "ok")]
        a2.hist(ok["coverage_mean"], np.linspace(0, 1, 41), histtype="step", color=COLORS.get(source), label=source)
    a1.set_yscale("log")
    a1.set_xlabel("model input value (covered pixels)")
    a1.legend(fontsize=7)
    a2.set_yscale("log")
    a2.set_xlabel("field coverage")
    fig.tight_layout()
    fig.savefig(out / "pixels.png", dpi=110)
    plt.close(fig)


def profiles(df, run, out, n_bins=24):
    import matplotlib.pyplot as plt

    cfg = run["config"]
    kpc = cfg["field"].get("kpc")
    if not kpc:
        return
    grid = int(cfg["grid"])
    base = Path(cfg.get("stage1_dir", preprocess.PREPROCESSED / "_stage1")) / run["spatial_hash"]
    yy, xx = np.indices((grid, grid))
    r_kpc = np.hypot(xx - (grid - 1) / 2, yy - (grid - 1) / 2) * kpc / grid
    edges = np.linspace(0, kpc / 2, n_bins + 1)
    which = np.digitize(r_kpc, edges) - 1
    zbins = redshift_bins(df)
    fig, axes = plt.subplots(1, max(1, len(zbins)), figsize=(4.2 * max(1, len(zbins)), 3.6), squeeze=False)
    for ax, (z, lo, hi) in zip(axes[0], zbins):
        for source in dict.fromkeys(df["source"]):
            sel = df[in_bin(df, lo, hi) & (df["source"] == source)]
            curves = []
            for name in sel["name"]:
                with np.load(base / source / f"{preprocess.safe_name(name)}.npz") as data:
                    sb, cov = data["sb"], data["coverage"]
                prof = [
                    sb[(which == k) & (cov >= 0.5)].mean() if ((which == k) & (cov >= 0.5)).any() else np.nan
                    for k in range(n_bins)
                ]
                curves.append(prof)
            if not curves:
                continue
            curves = np.array(curves)
            mid = 0.5 * (edges[1:] + edges[:-1])
            med = np.nanmedian(curves, axis=0)
            lo_q, hi_q = np.nanpercentile(curves, [16, 84], axis=0)
            color = COLORS.get(source)
            ax.plot(mid, med, color=color, label=f"{source} ({len(curves)})")
            ax.fill_between(mid, np.clip(lo_q, 1e-12, None), np.clip(hi_q, 1e-12, None), color=color, alpha=0.15)
        ax.set_yscale("log")
        ax.set_xlabel("r (kpc)")
        ax.set_title(f"z = {z:.2f} ± 0.025", fontsize=9)
        ax.legend(fontsize=7)
    axes[0, 0].set_ylabel("surface brightness (ph cm$^{-2}$ s$^{-1}$ arcsec$^{-2}$)")
    fig.tight_layout()
    fig.savefig(out / "profiles.png", dpi=110)
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", help="Figure directory (default: <run>/qa)")
    args = parser.parse_args(argv)
    run_dir = Path(args.run)
    out = Path(args.out or run_dir / "qa")
    out.mkdir(parents=True, exist_ok=True)
    df = manifest.read(run_dir)
    run = json.loads((run_dir / "run.json").read_text())
    examples(df, run_dir, out)
    pixels(df, run_dir, out)
    profiles(df, run, out)
    print(f"QA figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
