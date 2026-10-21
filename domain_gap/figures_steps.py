"""What the images look like at each step of harmonization and matching.

    python -m domain_gap.figures_steps harmonization [--examples LEMUR:A401 TNG300-1:0 ...]
    python -m domain_gap.figures_steps matching

harmonization_steps.png: one row per example, columns
  0. the original mock image (the earlier study's normalized PNG, cropped and
     re-normalized as in its TNG300 pipeline; TNG300 only, z = 0.05, 100 ks);
  1. the Chandra flux image at native resolution, 10' across, with the
     baseline's 4.2' field (dashed) and the 500 kpc field (solid);
  2.-4. the model inputs of the baseline, harmonized morphology and
     harmonized physical configurations.
Rows alternate LEMUR clusters and mocks.

matching_steps.png: for LEMUR clusters near each mock redshift, the
harmonized physical input (one display scale per row, set by the LEMUR
image; the two native cores share one too) next to the closest mock (either simulation, same
redshift and nearest exposure) when matching on (L), (L, c) and
(L, c, S/N, point-source fraction), then 100" native-resolution cores of the
LEMUR cluster and of the last mock, to compare PSF, noise and point sources by
eye. Each panel gives log L, c, S/N and point-source fraction.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import io, spatial

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figures" / "steps"
PREPROCESSED = io.DEFAULT_DATA / "_domain_gap" / "preprocessed"
STUDENT_PNGS = Path.home() / "friend-mac-recovery" / "tng_300_mocks_uncropped"
CONFIGS = [("baseline", "baseline\n(4.2', per image)"), ("harmonized_morphology", "harmonized morphology\n(500 kpc, per image)"),
           ("harmonized_physical", "harmonized physical\n(500 kpc, shared scale)")]
RAW_FIELD_ARCMIN = 10.0


def inputs_for(config, source, name):
    run = PREPROCESSED / config
    man = pd.read_parquet(run / "manifest.parquet")
    row = man[(man["source"] == source) & (man["name"] == name)]
    if not len(row) or row["index"].iloc[0] < 0:
        return None, None
    arr = np.load(run / f"inputs_{source}.npy", mmap_mode="r")
    return np.asarray(arr[int(row["index"].iloc[0])]), row.iloc[0]


def raw_cutout(row, half_arcmin=RAW_FIELD_ARCMIN / 2):
    """Native-resolution flux around the image centre, its pixel size, and the centre in the cutout."""
    from astropy.io import fits
    from astropy.wcs import WCS

    if row["source"] == io.LEMUR:
        flux_path, _ = io.lemur_files(Path(row["folder"]), "broad")
    else:
        flux_path = Path(row["folder"]) / "broad_flux.fits.gz"
    with fits.open(flux_path, memmap=True) as hdul:
        header = hdul[0].header
        wcs = WCS(header).celestial
        pix = io._pixel_arcsec(wcs)
        cx, cy = wcs.wcs_world2pix([[row["center_ra"], row["center_dec"]]], 0)[0]
        h = int(half_arcmin * 60 / pix)
        y0, x0 = max(0, int(cy) - h), max(0, int(cx) - h)
        data = np.asarray(hdul[0].data[y0 : int(cy) + h, x0 : int(cx) + h], dtype=np.float64)
    return data, pix, (cx - x0, cy - y0)


def show_raw(ax, data, pix, centre, boxes=(), limits=None):
    """Smoothed native-resolution flux, asinh-stretched; returns the (lo, hi) used,
    so a second panel can share the display scale."""
    from scipy.ndimage import gaussian_filter

    img = gaussian_filter(np.nan_to_num(data), 1.5)
    if limits is None:
        pos = img[img > 0]
        limits = tuple(np.percentile(pos, [5, 99.7])) if pos.size else (0.0, 1.0)
    lo, hi = limits
    shown = np.arcsinh(np.clip(img - lo, 0, None) / (0.05 * (hi - lo) + 1e-30))
    ax.imshow(shown, origin="lower", cmap="magma", vmin=0, vmax=np.arcsinh(1 / 0.05))
    for side_arcsec, style in boxes:
        s = side_arcsec / pix
        ax.add_patch(__import__("matplotlib").patches.Rectangle((centre[0] - s / 2, centre[1] - s / 2), s, s, fill=False,
                                                                 ec="w", ls=style, lw=0.8))
    return limits


def student_image(halo, proj):
    from PIL import Image

    path = STUDENT_PNGS / f"tng_300_{halo}_{proj}_proj_tng300_{halo}_cleaned_binned_normalized.png"
    if not path.exists():
        return None
    img = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
    c0, c1 = img.shape[0] // 2, img.shape[1] // 2
    crop = img[c0 - 126 : c0 + 126, c1 - 126 : c1 + 126]
    return (crop - crop.min()) / (np.ptp(crop) + 1e-12)


def harmonization(args):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    examples = [e.split(":", 1) for e in args.examples]
    rows = []
    for source, name in examples:
        if source != io.LEMUR and "_" not in name:  # a halo id: its x projection at z = 0.05, 100 ks
            name = f"{name}_x_z0.05_100ks"
        rows.append((source, name))
    cols = ["original pipeline", f"Chandra flux, {RAW_FIELD_ARCMIN:g}' (native)"] + [c[1] for c in CONFIGS]
    fig, axes = plt.subplots(len(rows), len(cols), figsize=(2.3 * len(cols), 2.45 * len(rows)), squeeze=False)
    for r, (source, name) in enumerate(rows):
        _, info = inputs_for("harmonized_physical", source, name)
        if info is None:
            _, info = inputs_for("baseline", source, name)
        for c in range(len(cols)):
            axes[r, c].set_xticks([])
            axes[r, c].set_yticks([])
        # 0: original pipeline
        if source == "TNG300-1":
            halo, proj = name.split("_")[:2]
            img = student_image(halo, proj)
            if img is not None:
                axes[r, 0].imshow(img, origin="upper", cmap="gray")
            else:
                axes[r, 0].text(0.5, 0.5, "not available", ha="center", va="center", fontsize=7, transform=axes[r, 0].transAxes)
        else:
            text = "same as baseline" if source == io.LEMUR else "not available"
            axes[r, 0].text(0.5, 0.5, text, ha="center", va="center", fontsize=7, transform=axes[r, 0].transAxes)
        # 1: raw flux with the two fields
        data, pix, centre = raw_cutout(info)
        side_500 = spatial.field_side_arcsec({"kpc": 500}, info["redshift"])
        show_raw(axes[r, 1], data, pix, centre, boxes=[(512 * spatial.ACIS_PIXEL_ARCSEC, "--"), (side_500, "-")])
        # 2-4: model inputs
        for c, (config, _) in enumerate(CONFIGS, start=2):
            img, _ = inputs_for(config, source, name)
            if img is not None:
                axes[r, c].imshow(img, origin="lower", cmap="magma", vmin=0, vmax=1)
        label = f"{'LEMUR' if source == io.LEMUR else source}\n{name}\nz = {info['redshift']:.3f}, {info['exposure_ks']:.0f} ks"
        axes[r, 0].set_ylabel(label, fontsize=7)
    for c, title in enumerate(cols):
        axes[0, c].set_title(title, fontsize=8)
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "harmonization_steps.png", dpi=130)
    plt.close(fig)
    print(f"Wrote {OUT / 'harmonization_steps.png'}")


# ---------------------------------------------------------------- matching


def matching_table(config="harmonized_physical"):
    lum = pd.read_csv(ROOT / "outputs" / "figures" / "mass" / "luminosities.csv")
    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    sig = pd.read_csv(ROOT / "outputs" / "figures" / "signal" / "signal.csv")
    man = pd.read_parquet(PREPROCESSED / config / "manifest.parquet")
    df = man[man["usable"] & (man["index"] >= 0)]
    df = df.merge(lum[["source", "name", "log_L_ph"]], on=["source", "name"]).merge(core, on=["source", "name"])
    df = df.merge(sig[["source", "name", "snr", "ps_fraction"]], on=["source", "name"])
    df = df[(df["snr"] >= 10) & ~(df["ps_fraction"] > 0.5)].copy()
    df["log_c"] = np.log10(df["c40_250"].where(df["c40_250"] > 0))
    df["log_snr"] = np.log10(df["snr"])
    return df.dropna(subset=["log_L_ph", "log_c", "log_snr", "ps_fraction"])


def nearest(lemur_row, mocks, cols, scales):
    d = sum(((mocks[c] - lemur_row[c]) / s) ** 2 for c, s in zip(cols, scales))
    return mocks.loc[d.idxmin()]


def matching(args):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from . import mass_match as mm

    df = matching_table(args.config)
    picks = []
    if args.names:
        for name in args.names:
            row = df[(df["source"] == "LEMUR") & (df["name"] == name)]
            if len(row):
                z = min((0.05, 0.1, 0.2), key=lambda v: abs(v - row["redshift"].iloc[0]))
                picks.append((z, row.iloc[0]))
            else:
                print(f"{name}: not in the matched sample (z, signal cut), skipped")
    for z in (() if args.names else (0.05, 0.1, 0.2)):
        lemur = df[(df["source"] == "LEMUR") & ((df["redshift"] - z).abs() < 0.025)]
        # Spread the examples over luminosity: low, middle and high.
        lemur = lemur.sort_values("log_L_ph")
        idx = np.linspace(0.15, 0.85, args.per_z) * (len(lemur) - 1)
        picks += [(z, lemur.iloc[int(round(i))]) for i in idx]
    levels = [("matched L, exposure", ["log_L_ph"], [0.2]),
              ("+ concentration", ["log_L_ph", "log_c"], [0.2, 0.15]),
              ("+ S/N, point sources", ["log_L_ph", "log_c", "log_snr", "ps_fraction"], [0.2, 0.15, 0.3, 0.1])]
    cols = ["LEMUR"] + [lvl[0] for lvl in levels] + ['LEMUR core, 100" native', 'last mock core, 100" native']
    fig, axes = plt.subplots(len(picks), len(cols), figsize=(2.2 * len(cols), 2.35 * len(picks)), squeeze=False)

    def describe(row):
        return f"logL {row['log_L_ph']:.2f}  c {row['c40_250']:.2f}\nS/N {row['snr']:.0f}  ps {row['ps_fraction']:.2f}"

    for r, (z, lrow) in enumerate(picks):
        mocks = df[(df["source"] != "LEMUR") & (df["redshift"] == z)]
        exposure = mm.nearest_exposure(lrow["exposure_ks"], sorted(mocks["exposure_ks"].unique()))
        mocks = mocks[mocks["exposure_ks"] == exposure]
        img, _ = inputs_for(args.config, "LEMUR", lrow["name"])
        # One display scale per row, set by the LEMUR image, so faint clusters
        # are visible and the panels of a row stay comparable.
        row_max = max(float(np.percentile(img, 99.7)), 0.05)
        axes[r, 0].imshow(img, origin="lower", cmap="magma", vmin=0, vmax=row_max)
        axes[r, 0].set_ylabel(f"{lrow['name']}\nz = {lrow['redshift']:.3f}, {lrow['exposure_ks']:.0f} ks", fontsize=7)
        axes[r, 0].set_xlabel(describe(lrow), fontsize=6)
        last = None
        for c, (label, mcols, scales) in enumerate(levels, start=1):
            m = nearest(lrow, mocks, mcols, scales)
            img, _ = inputs_for(args.config, m["source"], m["name"])
            axes[r, c].imshow(img, origin="lower", cmap="magma", vmin=0, vmax=row_max)
            axes[r, c].set_xlabel(f"{m['source']} {m['name']}\n" + describe(m), fontsize=6)
            last = m
        limits = None
        for c, row in [(len(levels) + 1, lrow), (len(levels) + 2, last)]:
            data, pix, centre = raw_cutout(row, half_arcmin=50 / 60)
            limits = show_raw(axes[r, c], data, pix, centre, limits=limits)
            axes[r, c].set_xlabel(f"{pix:.3f}\"/px", fontsize=6)
        for c in range(len(cols)):
            axes[r, c].set_xticks([])
            axes[r, c].set_yticks([])
    for c, title in enumerate(cols):
        axes[0, c].set_title(title, fontsize=8)
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / args.out_name, dpi=120)
    plt.close(fig)
    print(f"Wrote {OUT / args.out_name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    h = sub.add_parser("harmonization")
    h.add_argument("--examples", nargs="*", default=["LEMUR:A401", "TNG300-1:0", "LEMUR:Abell2029", "TNG300-1:190"])
    m = sub.add_parser("matching")
    m.add_argument("--config", default="harmonized_physical", help="Preprocessing run whose inputs are shown")
    m.add_argument("--names", nargs="*", help="LEMUR clusters to show (default: two per redshift, spread in L)")
    m.add_argument("--out-name", default="matching_steps.png")
    m.add_argument("--per-z", type=int, default=2)
    m.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    {"harmonization": harmonization, "matching": matching}[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
