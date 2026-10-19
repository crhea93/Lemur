"""How far apart LEMUR and the TNG mocks are in AstroCLIP embedding space.

    python -m domain_gap.analyze_embeddings [--runs outputs/embeddings/<config> ...]
        [--out outputs/figures/embeddings]

For each run (preprocessing config) and each mock redshift, LEMUR clusters
within +-0.025 of it are compared with the mocks at that redshift (usable
images only, embeddings L2-normalized):

- pca_<config>.png: the first two principal components, by source;
- domain_auc.png: how well a linear classifier tells two sources apart
  (cross-validated ROC AUC; 0.5 = indistinguishable). Folds keep all images of
  one halo (or LEMUR object) together, so projections and exposures of the same
  halo cannot leak between training and testing. TNG300 vs TNG-Cluster gives a
  simulation-to-simulation reference;
- nn_<config>.png: for each LEMUR cluster, the cosine similarity of its nearest
  mock and of its nearest other LEMUR cluster;
- domain_auc.csv: the numbers.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"LEMUR": "k", "TNG300-1": "tab:blue", "TNG-Cluster": "tab:red"}
Z_WIDTH = 0.025


def load_run(run_dir):
    """Usable manifest rows with their L2-normalized embeddings, and the run name."""
    run_dir = Path(run_dir)
    df = pd.read_parquet(run_dir / "manifest.parquet")
    df = df[df["usable"] & (df["index"] >= 0)].copy()
    vectors = np.zeros((len(df), 0), np.float32)
    parts = []
    for source, rows in df.groupby("source", sort=False):
        emb = np.load(run_dir / f"embeddings_{source}.npy")
        parts.append((rows.index, emb[rows["index"].astype(int).to_numpy()]))
    if parts:
        dim = parts[0][1].shape[1]
        vectors = np.zeros((len(df), dim), np.float32)
        position = {label: i for i, label in enumerate(df.index)}
        for labels, emb in parts:
            vectors[[position[label] for label in labels]] = emb
        vectors /= np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    df["group"] = np.where(
        df["source"] == "LEMUR",
        df["name"],
        df["source"] + ":" + df.get("halo_id", pd.Series(index=df.index, dtype=float)).astype("Int64").astype(str),
    )
    name = json.loads((run_dir / "run.json").read_text())["config"]["name"]
    return df.reset_index(drop=True), vectors, name


def mock_redshifts(df):
    return sorted(df.loc[df["source"] != "LEMUR", "redshift"].dropna().unique())


def matched(df, z):
    near = (df["redshift"] - z).abs() < Z_WIDTH + 1e-9
    return np.where((df["source"] == "LEMUR") & near | (df["source"] != "LEMUR") & (df["redshift"] == z))[0]


# ---------------------------------------------------------------- classifier


def _fit_logistic(x, y, weights, l2):
    from scipy.optimize import minimize

    def loss(w):
        z = x @ w[:-1] + w[-1]
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        eps = 1e-12
        value = -np.sum(weights * (y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))
        grad_z = weights * (p - y)
        grad = np.concatenate([x.T @ grad_z + l2 * w[:-1], [grad_z.sum()]])
        return value + 0.5 * l2 * np.sum(w[:-1] ** 2), grad

    result = minimize(loss, np.zeros(x.shape[1] + 1), jac=True, method="L-BFGS-B")
    return result.x


def auc(scores, labels):
    """ROC AUC by the Mann-Whitney statistic (ties count one half)."""
    from scipy.stats import rankdata

    labels = np.asarray(labels, bool)
    n1, n0 = labels.sum(), (~labels).sum()
    if n1 == 0 or n0 == 0:
        return np.nan
    ranks = rankdata(scores)
    return float((ranks[labels].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def domain_auc(x, labels, groups, folds=5, l2=1.0, seed=0):
    """Grouped k-fold cross-validated AUC of a class-balanced logistic regression."""
    labels = np.asarray(labels, float)
    unique = np.unique(groups)
    if len(unique) < folds or labels.sum() < 5 or (1 - labels).sum() < 5:
        return np.nan
    rng = np.random.default_rng(seed)
    fold_of = dict(zip(rng.permutation(unique), np.arange(len(unique)) % folds))
    fold = np.array([fold_of[g] for g in groups])
    scores = np.zeros(len(labels))
    for k in range(folds):
        train, test = fold != k, fold == k
        if not test.any() or len(np.unique(labels[train])) < 2:
            return np.nan
        y = labels[train]
        weights = np.where(y == 1, 0.5 / y.sum(), 0.5 / (1 - y).sum()) * len(y)
        mean = x[train].mean(axis=0)
        w = _fit_logistic(x[train] - mean, y, weights, l2)
        scores[test] = (x[test] - mean) @ w[:-1] + w[-1]
    return auc(scores, labels)


# ---------------------------------------------------------------- figures


def pca_figure(df, x, name, out):
    import matplotlib.pyplot as plt

    zs = mock_redshifts(df)
    if not zs:
        return
    fig, axes = plt.subplots(1, len(zs), figsize=(4.4 * len(zs), 4.2), squeeze=False)
    for ax, z in zip(axes[0], zs):
        idx = matched(df, z)
        sub = df.iloc[idx]
        # Fit on equal numbers per source so the larger sample does not set the axes.
        rng = np.random.default_rng(0)
        n = min(sub["source"].value_counts())
        fit = np.concatenate(
            [rng.choice(np.where(sub["source"].to_numpy() == s)[0], n, replace=False) for s in sub["source"].unique()]
        )
        xs = x[idx]
        mean = xs[fit].mean(axis=0)
        _, _, vt = np.linalg.svd(xs[fit] - mean, full_matrices=False)
        proj = (xs - mean) @ vt[:2].T
        for source in ["TNG300-1", "TNG-Cluster", "LEMUR"]:
            m = sub["source"].to_numpy() == source
            if m.any():
                ax.scatter(
                    proj[m, 0], proj[m, 1], s=6 if source != "LEMUR" else 12,
                    c=COLORS[source], alpha=0.35 if source != "LEMUR" else 0.9,
                    label=f"{source} ({m.sum()})", linewidths=0,
                )
        ax.set_title(f"{name}: z = {z:.2f}", fontsize=9)
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.legend(fontsize=7, markerscale=2)
    fig.tight_layout()
    fig.savefig(out / f"pca_{name}.png", dpi=120)
    plt.close(fig)


def nn_figure(df, x, name, out):
    import matplotlib.pyplot as plt

    zs = mock_redshifts(df)
    if not zs:
        return
    fig, axes = plt.subplots(1, len(zs), figsize=(4.4 * len(zs), 3.6), squeeze=False)
    bins = np.linspace(0, 1, 51)
    for ax, z in zip(axes[0], zs):
        idx = matched(df, z)
        sub = df.iloc[idx]
        is_lemur = sub["source"].to_numpy() == "LEMUR"
        if is_lemur.sum() < 2:
            continue
        sim = x[idx][is_lemur] @ x[idx].T
        lemur_cols = np.where(is_lemur)[0]
        sim[np.arange(len(lemur_cols)), lemur_cols] = -np.inf  # not itself
        best_lemur = sim[:, is_lemur].max(axis=1)
        ax.hist(best_lemur, bins, histtype="step", color="k", label="nearest LEMUR")
        for source in ["TNG300-1", "TNG-Cluster"]:
            cols = sub["source"].to_numpy() == source
            if cols.any():
                ax.hist(sim[:, cols].max(axis=1), bins, histtype="step", color=COLORS[source], label=f"nearest {source}")
        ax.set_title(f"{name}: LEMUR at z = {z:.2f} (n={is_lemur.sum()})", fontsize=9)
        ax.set_xlabel("cosine similarity of nearest neighbour")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / f"nn_{name}.png", dpi=120)
    plt.close(fig)


def auc_table(runs):
    rows = []
    pairs = [("LEMUR", "TNG300-1"), ("LEMUR", "TNG-Cluster"), ("TNG300-1", "TNG-Cluster")]
    for df, x, name in runs:
        for z in mock_redshifts(df):
            idx = matched(df, z)
            sub = df.iloc[idx]
            for a, b in pairs:
                m = sub["source"].isin([a, b]).to_numpy()
                labels = (sub["source"].to_numpy()[m] == a).astype(float)
                rows.append(
                    {
                        "config": name,
                        "redshift": z,
                        "pair": f"{a} vs {b}",
                        "n_a": int(labels.sum()),
                        "n_b": int((1 - labels).sum()),
                        "auc": domain_auc(x[idx][m], labels, sub["group"].to_numpy()[m]),
                    }
                )
    return pd.DataFrame(rows)


def auc_figure(table, out):
    import matplotlib.pyplot as plt

    configs = list(dict.fromkeys(table["config"]))
    pairs = list(dict.fromkeys(table["pair"]))
    zs = sorted(table["redshift"].unique())
    fig, axes = plt.subplots(1, len(pairs), figsize=(4.6 * len(pairs), 3.6), squeeze=False, sharey=True)
    width = 0.8 / max(1, len(configs))
    for ax, pair in zip(axes[0], pairs):
        for i, config in enumerate(configs):
            sel = table[(table["pair"] == pair) & (table["config"] == config)].set_index("redshift")
            ax.bar(np.arange(len(zs)) + i * width, [sel["auc"].get(z, np.nan) for z in zs], width, label=config)
        ax.axhline(0.5, color="gray", lw=0.8, ls="--")
        ax.set_xticks(np.arange(len(zs)) + width * (len(configs) - 1) / 2, [f"z={z:.2f}" for z in zs])
        ax.set_ylim(0.4, 1.0)
        ax.set_title(pair, fontsize=9)
    axes[0, 0].set_ylabel("domain classifier AUC")
    axes[0, -1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "domain_auc.png", dpi=120)
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default_runs = [str(p) for p in sorted((ROOT / "outputs" / "embeddings").glob("*")) if (p / "run.json").exists()]
    parser.add_argument("--runs", nargs="*", default=default_runs)
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "embeddings"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runs = [load_run(r) for r in args.runs]
    for df, x, name in runs:
        print(f"{name}: " + ", ".join(f"{s} {n}" for s, n in df["source"].value_counts().items()))
        pca_figure(df, x, name, out)
        nn_figure(df, x, name, out)
    table = auc_table(runs)
    table.to_csv(out / "domain_auc.csv", index=False)
    auc_figure(table, out)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"Figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
