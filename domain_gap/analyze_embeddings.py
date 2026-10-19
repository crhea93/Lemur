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


def load_run(run_dir, signal_cut=None):
    """Usable manifest rows with their L2-normalized embeddings, and the run name.

    ``signal_cut`` = (signal table, snr_min, ps_max) also applies the signal
    cut of ``domain_gap.signal`` (the same for every source).
    """
    run_dir = Path(run_dir)
    df = pd.read_parquet(run_dir / "manifest.parquet")
    df = df[df["usable"] & (df["index"] >= 0)].copy()
    if signal_cut is not None:
        from .signal import select

        df = select(df, *signal_cut).copy()
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


# Probe used by domain_auc when none is given: "linear" (logistic regression) or
# "mlp" (one hidden layer), set by the analyses' --probe option.
PROBE = "linear"
MLP_HIDDEN = 64
MLP_MAXITER = 300


def _fit_mlp(x, y, weights, l2, hidden=MLP_HIDDEN, seed=0, maxiter=MLP_MAXITER):
    """One-hidden-layer ReLU network, weighted cross-entropy + L2, fitted by L-BFGS.

    Returns a function mapping features to logits.
    """
    from scipy.optimize import minimize

    rng = np.random.default_rng(seed)
    d = x.shape[1]
    shapes = [(d, hidden), (hidden,), (hidden,), (1,)]
    sizes = [int(np.prod(s)) for s in shapes]
    w0 = np.concatenate(
        [rng.normal(0, np.sqrt(2.0 / d), sizes[0]), np.zeros(sizes[1]),
         rng.normal(0, np.sqrt(1.0 / hidden), sizes[2]), np.zeros(1)]
    )

    def unpack(w):
        parts, i = [], 0
        for shape, size in zip(shapes, sizes):
            parts.append(w[i : i + size].reshape(shape))
            i += size
        return parts

    def loss(w):
        w1, b1, w2, b2 = unpack(w)
        pre = x @ w1 + b1
        h = np.maximum(pre, 0.0)
        z = h @ w2 + b2[0]
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        eps = 1e-12
        value = -np.sum(weights * (y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))
        value += 0.5 * l2 * (np.sum(w1**2) + np.sum(w2**2))
        dz = weights * (p - y)
        dh = np.outer(dz, w2) * (pre > 0)
        grad = np.concatenate(
            [(x.T @ dh + l2 * w1).ravel(), dh.sum(axis=0), h.T @ dz + l2 * w2, [dz.sum()]]
        )
        return value, grad

    w = minimize(loss, w0, jac=True, method="L-BFGS-B", options={"maxiter": maxiter}).x
    w1, b1, w2, b2 = unpack(w)
    return lambda features: np.maximum(features @ w1 + b1, 0.0) @ w2 + b2[0]


def auc(scores, labels, weights=None):
    """ROC AUC by the (weighted) Mann-Whitney statistic; ties count one half."""
    labels = np.asarray(labels, bool)
    weights = np.ones(len(labels)) if weights is None else np.asarray(weights, float)
    w1, w0 = weights[labels].sum(), weights[~labels].sum()
    if w1 == 0 or w0 == 0:
        return np.nan
    order = np.argsort(scores, kind="mergesort")
    s, lab, w = np.asarray(scores)[order], labels[order], weights[order]
    # For each positive: weight of negatives below it, plus half of those tied.
    neg_w = np.where(lab, 0.0, w)
    below = np.cumsum(neg_w) - neg_w
    _, first, counts = np.unique(s, return_index=True, return_counts=True)
    tie_neg = np.add.reduceat(neg_w, first)
    tie_start = np.repeat(below[first], counts)
    tie_total = np.repeat(tie_neg, counts)
    wins = tie_start + 0.5 * tie_total
    return float((w[lab] * wins[lab]).sum() / (w1 * w0))


def domain_auc_ci(x, labels, groups, weights=None, n_boot=1000, level=0.68, seed=1, **kwargs):
    """(AUC, low, high): ``domain_auc`` with a bootstrap interval.

    The out-of-fold scores are computed once; groups (halos, LEMUR objects) are
    then resampled with replacement within each class and the weighted AUC
    recomputed. This covers the sampling uncertainty of the AUC, not the
    variance from retraining the classifier.
    """
    result = domain_auc(x, labels, groups, weights=weights, return_scores=True, **kwargs)
    if not isinstance(result, tuple):
        return result, np.nan, np.nan
    value, scores, lab, grp, w = result
    rng = np.random.default_rng(seed)
    members = {}
    for i, g in enumerate(grp):
        members.setdefault((lab[i], g), []).append(i)
    by_class = {c: [members[k] for k in members if k[0] == c] for c in (0.0, 1.0)}
    draws = []
    for _ in range(n_boot):
        idx = np.concatenate(
            [np.concatenate([groups_c[j] for j in rng.integers(0, len(groups_c), len(groups_c))]) for groups_c in by_class.values()]
        )
        draws.append(auc(scores[idx], lab[idx].astype(bool), w[idx]))
    lo, hi = np.nanpercentile(draws, [50 * (1 - level), 50 * (1 + level)])
    return value, float(lo), float(hi)


def null_auc(x, labels, groups, weights=None, n_perm=50, seed=2, strata=None, **kwargs):
    """(mean, 16th, 84th percentile) of ``domain_auc`` with the class labels permuted.

    Labels are shuffled between groups (keeping the number of groups per class),
    so the null keeps the group structure and sample sizes of the real test.
    With ``strata`` (one key per row, e.g. the reweighting bin), labels are
    shuffled only among groups in the same stratum, a group belonging to its
    rows' most common stratum. Reweighted comparisons need this: their classes
    are balanced bin by bin, and holding out one object leaves its bin
    unbalanced, which biases cross-validated AUCs below 0.5 in a way a global
    shuffle does not reproduce. Compare a measured AUC with this distribution.
    """
    labels = np.asarray(labels, float)
    groups = np.asarray(groups)
    group_ids, first = np.unique(groups, return_index=True)
    group_label = labels[first]
    if strata is None:
        group_stratum = np.zeros(len(group_ids), dtype=object)
    else:
        keys = pd.Series([repr(k) if k is not None else None for k in strata])
        modal = keys.groupby(pd.Series(groups)).agg(lambda v: v.dropna().mode().iloc[0] if v.notna().any() else "none")
        group_stratum = modal.reindex(group_ids).to_numpy()
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n_perm):
        perm_label = group_label.copy()
        for stratum in pd.unique(group_stratum):
            idx = np.where(group_stratum == stratum)[0]
            perm_label[idx] = rng.permutation(group_label[idx])
        shuffled = dict(zip(group_ids, perm_label))
        perm = np.array([shuffled[g] for g in groups])
        values.append(domain_auc(x, perm, groups, weights=weights, strata=strata, **kwargs))
    values = np.asarray(values, float)
    return float(np.nanmean(values)), *(float(v) for v in np.nanpercentile(values, [16, 84]))


def domain_auc(x, labels, groups, folds=5, l2=1.0, seed=0, weights=None, return_scores=False, probe=None, strata=None):
    """Grouped k-fold cross-validated AUC of a class-balanced classifier.

    ``probe`` is "linear" (logistic regression) or "mlp" (one hidden layer);
    default PROBE. ``weights`` (optional, per sample) reweight both the fit and
    the AUC, e.g. to give two samples the same mass distribution.
    ``strata`` (optional, one key per sample: the reweighting bin) rebalances
    the two classes within every stratum of each TRAINING fold. Weights made
    to balance the full sample bin by bin are unbalanced once a fold is held
    out, and a classifier then learns which bins hold more of one class, which
    pushes held-out scores, and the AUC, below 0.5 without any signal.
    ``return_scores`` also returns the out-of-fold scores, labels, groups and
    weights used.
    """
    probe = probe or PROBE
    labels = np.asarray(labels, float)
    sample_w = np.ones(len(labels)) if weights is None else np.asarray(weights, float)
    keep = sample_w > 0
    x, labels, groups, sample_w = x[keep], labels[keep], np.asarray(groups)[keep], sample_w[keep]
    strata_arr = None if strata is None else np.array([repr(k) for k in strata], dtype=object)[keep]
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
        y, sw = labels[train], sample_w[train]
        if strata_arr is not None:
            sw = sw.copy()
            st = strata_arr[train]
            for key in np.unique(st):
                in_key = st == key
                w1, w0 = sw[in_key & (y == 1)].sum(), sw[in_key & (y == 0)].sum()
                if w1 == 0 or w0 == 0:
                    sw[in_key] = 0.0
                else:
                    sw[in_key & (y == 0)] *= w1 / w0
            if sw[y == 1].sum() == 0 or sw[y == 0].sum() == 0:
                return np.nan
        balance = np.where(y == 1, 0.5 / sw[y == 1].sum(), 0.5 / sw[y == 0].sum())
        mean = x[train].mean(axis=0)
        if probe == "mlp":
            predict = _fit_mlp(x[train] - mean, y, sw * balance * len(y), l2, seed=seed + k)
            scores[test] = predict(x[test] - mean)
        else:
            w = _fit_logistic(x[train] - mean, y, sw * balance * len(y), l2)
            scores[test] = (x[test] - mean) @ w[:-1] + w[-1]
    value = auc(scores, labels, sample_w)
    if return_scores:
        return value, scores, labels, groups, sample_w
    return value


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


def add_signal_args(parser):
    parser.add_argument(
        "--signal-cut",
        nargs="?",
        const=str(ROOT / "outputs" / "figures" / "signal" / "signal.csv"),
        help="Apply the signal cut of domain_gap.signal (optionally: path to signal.csv)",
    )
    parser.add_argument("--snr-min", type=float, default=10.0)
    parser.add_argument("--ps-max", type=float, default=0.5)


def signal_cut(args):
    if not args.signal_cut:
        return None
    return (pd.read_csv(args.signal_cut), args.snr_min, args.ps_max)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default_runs = [str(p) for p in sorted((ROOT / "outputs" / "embeddings").glob("*")) if (p / "run.json").exists()]
    parser.add_argument("--runs", nargs="*", default=default_runs)
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "embeddings"))
    add_signal_args(parser)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runs = [load_run(r, signal_cut(args)) for r in args.runs]
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
