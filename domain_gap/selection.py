"""Does the cool-core excess of LEMUR come from how its targets were selected?

    python -m domain_gap.selection [--out outputs/figures/selection]

LEMUR clusters are cross-matched with Planck PSZ2 (SZ detected: roughly mass
limited and insensitive to the core) and MCXC (ROSAT X-ray detected, which
favours cool cores at a given mass): within 5' and |dz| < 0.02 for PSZ2 (Planck
positions), 3' and |dz| < 0.02 for MCXC. Catalogs (VizieR J/A+A/594/A27,
J/A+A/534/A109) are read from outputs/catalogs/.

- mass_check.png: TNG-calibrated LEMUR masses (domain_gap.mass_match) against
  the PSZ2 SZ masses and MCXC masses of the same clusters.
- selection_core.png / selection_core.csv: the concentration of LEMUR clusters
  in and not in PSZ2, against mocks reweighted to each subsample's (L,
  exposure), at each mock redshift: median c and the fraction with c > 0.15
  (the high-concentration mode that L-matched mocks lack). If the PSZ2
  clusters look like the mocks and the others do not, the excess is selection.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import analyze_embeddings as ae
from . import core as core_mod
from . import mass_match as mm
from .plotting import save_figure

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ROOT / "outputs" / "catalogs"
C_HIGH = 0.15


def read_vizier_tsv(path):
    """A VizieR asu-tsv file (header, units and dashes lines after the comments)."""
    lines = [l for l in Path(path).read_text().splitlines() if l and not l.startswith("#")]
    header = lines[0].split("\t")
    rows = [l.split("\t") for l in lines[3:]]
    df = pd.DataFrame(rows, columns=header)
    for col in df.columns:
        converted = pd.to_numeric(df[col].str.strip(), errors="coerce")
        if converted.notna().mean() > 0.5:
            df[col] = converted
        else:
            df[col] = df[col].str.strip()
    return df.rename(columns={"_RAJ2000": "ra", "_DEJ2000": "dec"})


def crossmatch(lemur, catalog, radius_arcmin, dz):
    """Index of the nearest catalog entry within radius and |dz| (or -1) per LEMUR row."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    lc = SkyCoord(lemur["center_ra"].to_numpy() * u.deg, lemur["center_dec"].to_numpy() * u.deg)
    cc = SkyCoord(catalog["ra"].to_numpy() * u.deg, catalog["dec"].to_numpy() * u.deg)
    out = np.full(len(lemur), -1)
    idx_l, idx_c, sep, _ = cc.search_around_sky(lc, radius_arcmin * u.arcmin)
    best = {}
    for i, j, s in zip(idx_l, idx_c, sep.arcmin):
        zc = catalog["z"].iloc[j]
        zl = lemur["redshift"].iloc[i]
        if np.isfinite(zc) and zc > 0 and np.isfinite(zl) and abs(zc - zl) > dz:
            continue
        if i not in best or s < best[i][1]:
            best[i] = (j, s)
    for i, (j, _) in best.items():
        out[i] = j
    return out


def lemur_table(manifest_path):
    m = pd.read_parquet(manifest_path)
    lemur = m[(m["source"] == "LEMUR") & m["center_ra"].notna()].reset_index(drop=True)
    psz2 = read_vizier_tsv(CATALOGS / "psz2.tsv")
    mcxc = read_vizier_tsv(CATALOGS / "mcxc.tsv")
    ip = crossmatch(lemur, psz2, 5.0, 0.02)
    im = crossmatch(lemur, mcxc, 3.0, 0.02)
    lemur["in_psz2"] = ip >= 0
    lemur["in_mcxc"] = im >= 0
    msz = psz2["MSZ"].to_numpy()
    lemur["log_M_SZ"] = np.where(ip >= 0, np.log10(np.where(ip >= 0, msz[np.maximum(ip, 0)], np.nan) * 1e14), np.nan)
    m500 = mcxc["M500"].to_numpy()
    lemur["log_M_MCXC"] = np.where(im >= 0, np.log10(m500[np.maximum(im, 0)] * 1e14), np.nan)
    return lemur[["name", "redshift", "in_psz2", "in_mcxc", "log_M_SZ", "log_M_MCXC"]]


def mass_check_figure(table, masses, out):
    import matplotlib.pyplot as plt

    t = masses.merge(table, on="name", how="inner")
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
    stats = {}
    for ax, col, label in [(axes[0], "log_M_SZ", "PSZ2 SZ mass"), (axes[1], "log_M_MCXC", "MCXC mass")]:
        s = t.dropna(subset=[col, "log_M500_est"])
        diff = s["log_M500_est"] - s[col]
        stats[col] = (len(s), float(diff.median()), float(1.4826 * (diff - diff.median()).abs().median()))
        ax.scatter(s[col], s["log_M500_est"], s=10, c=s["z_bin"], cmap="viridis")
        lim = [13.0, 15.5]
        ax.plot(lim, lim, "k--", lw=0.8)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel(f"log {label} [M$_\\odot$]")
        ax.set_title(f"n={stats[col][0]}: offset {stats[col][1]:+.2f}, scatter {stats[col][2]:.2f} dex", fontsize=9)
    axes[0].set_ylabel(r"log $M_{500}$, TNG-calibrated from $L_{\rm ph}$")
    fig.tight_layout()
    save_figure(fig, out / "mass_check.png")
    plt.close(fig)
    return stats


def subsample_core(run, lum, core, table, l_bin):
    """Median c and high-c fraction of LEMUR subsamples and of mocks reweighted to each."""
    df, x, name = run
    df = core_mod.prepare(df, lum, core).merge(table[["name", "in_psz2", "in_mcxc"]], on="name", how="left")
    rows = []
    for z in ae.mock_redshifts(df):
        sub = df.iloc[ae.matched(df, z)]
        lemur_all = sub[sub["source"] == "LEMUR"]
        exposures = sorted(sub.loc[sub["source"] != "LEMUR", "exposure_ks"].unique())
        for label, lemur in [
            ("all", lemur_all),
            ("in PSZ2", lemur_all[lemur_all["in_psz2"] == True]),  # noqa: E712
            ("not in PSZ2", lemur_all[lemur_all["in_psz2"] != True]),  # noqa: E712
            ("MCXC, not PSZ2", lemur_all[(lemur_all["in_mcxc"] == True) & (lemur_all["in_psz2"] != True)]),  # noqa: E712
        ]:
            if len(lemur) < 5:
                continue
            cls = [mm.nearest_exposure(e, exposures) for e in lemur["exposure_ks"]]
            for sim in ["TNG300-1", "TNG-Cluster"]:
                s = sub[sub["source"] == sim]
                wl, ws = core_mod.reweight_nd([lemur["log_L_ph"]], cls, [s["log_L_ph"]], s["exposure_ks"], [l_bin])
                keep = wl > 0
                rows.append(
                    {
                        "redshift": z, "lemur": label, "sim": sim,
                        "n_lemur": int(keep.sum()), "n_eff_mock": round(mm.n_eff(ws), 1),
                        "lemur_median_c": core_mod.weighted_quantile(lemur["c40_250"], wl, 0.5),
                        "mock_median_c": core_mod.weighted_quantile(s["c40_250"], ws, 0.5),
                        "lemur_frac_high_c": float(np.average(lemur["c40_250"][keep] > C_HIGH)) if keep.any() else np.nan,
                        "mock_frac_high_c": float(np.average(s["c40_250"] > C_HIGH, weights=ws)) if ws.sum() > 0 else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def core_figure(table, out):
    import matplotlib.pyplot as plt

    zs = sorted(table["redshift"].unique())
    labels = list(dict.fromkeys(table["lemur"]))
    fig, axes = plt.subplots(1, len(zs), figsize=(4.4 * len(zs), 3.6), squeeze=False, sharey=True)
    for ax, z in zip(axes[0], zs):
        t = table[table["redshift"] == z]
        pos = np.arange(len(labels))
        for shift, sim, color in [(-0.27, None, "k"), (0.0, "TNG300-1", "tab:blue"), (0.27, "TNG-Cluster", "tab:red")]:
            if sim is None:
                vals = [t[(t["lemur"] == l) & (t["sim"] == "TNG300-1")]["lemur_frac_high_c"].mean() for l in labels]
                label = "LEMUR"
            else:
                vals = [t[(t["lemur"] == l) & (t["sim"] == sim)]["mock_frac_high_c"].mean() for l in labels]
                label = f"{sim}, L-matched"
            ax.bar(pos + shift, vals, 0.27, color=color, label=label)
        ns = [int(t[(t["lemur"] == l) & (t["sim"] == "TNG300-1")]["n_lemur"].max()) if len(t[t["lemur"] == l]) else 0 for l in labels]
        ax.set_xticks(pos, [f"{l}\n(n={n})" for l, n in zip(labels, ns)], fontsize=7)
        ax.set_title(f"z = {z:.2f}", fontsize=9)
    axes[0, 0].set_ylabel(f"fraction with c > {C_HIGH}")
    axes[0, 0].legend(fontsize=7)
    fig.tight_layout()
    save_figure(fig, out / "selection_core.png")
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", default=str(ROOT / "outputs" / "embeddings" / "harmonized_physical"))
    parser.add_argument("--out", default=str(ROOT / "outputs" / "figures" / "selection"))
    parser.add_argument("--l-bin", type=float, default=0.2)
    parser.add_argument("--no-signal-cut", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table = lemur_table(Path(args.run) / "manifest.parquet")
    table.to_csv(out / "lemur_catalog_matches.csv", index=False)
    with_z = table[table["redshift"].notna()]
    print(f"LEMUR with redshift: {len(with_z)}; in PSZ2 {int(with_z['in_psz2'].sum())}, in MCXC {int(with_z['in_mcxc'].sum())}, both {int((with_z['in_psz2'] & with_z['in_mcxc']).sum())}")
    masses = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "lemur_masses.csv")
    stats = mass_check_figure(table, masses, out)
    for col, (n, off, sc) in stats.items():
        print(f"TNG-calibrated vs {col}: n={n}, median offset {off:+.2f} dex, robust scatter {sc:.2f} dex")
    lum = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    cut = None if args.no_signal_cut else (pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv"), 10.0, 0.5)
    run = ae.load_run(args.run, cut)
    result = subsample_core(run, lum, core, table, args.l_bin)
    result.to_csv(out / "selection_core.csv", index=False)
    core_figure(result, out)
    print(result.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"Figures in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
