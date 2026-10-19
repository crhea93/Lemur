"""Signal quality of every image, measured identically for LEMUR and the mocks.

    python -m domain_gap.signal [--workers 6] [--out outputs/figures/signal]

Within r < 250 kpc of each image's centre (the centre used in preprocessing):

- net_counts = C - B and snr = (C - B) / sqrt(C), from the broad-band counts and
  background images (LEMUR: broad_thresh.img and broad_bkg.img; mocks:
  {band}_counts and BKGSCAL x the reference background);
- ps_fraction: the share of the aperture's net flux in compact sources, found by
  LEMUR's own point-source detector (``_point_source_mask`` of the AstroCLIP
  centring code) on the flux image binned to 3.9", with 120" of surroundings
  for its local statistics.

Writes signal.csv (cached) and signal.png (distributions by source and
redshift). ``select`` applies a cut to a manifest, so analyze_embeddings and
mass_match can use the same selection on both sides.
"""

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from . import io, spatial

ROOT = Path(__file__).resolve().parents[1]
APERTURE_KPC = 250.0
MARGIN_ARCSEC = 120.0
DEFAULT_OUT = ROOT / "outputs" / "figures" / "signal"
SNR_MIN = 10.0
PS_MAX = 0.5


def _read_box(path, y0, y1, x0, x1):
    from astropy.io import fits

    with fits.open(path, memmap=True) as hdul:
        return np.asarray(hdul[0].data[y0:y1, x0:x1], dtype=np.float64)


def _box(center_xy, half, shape):
    ny, nx = shape
    x0, x1 = max(0, int(center_xy[0] - half)), min(nx, int(center_xy[0] + half) + 1)
    y0, y1 = max(0, int(center_xy[1] - half)), min(ny, int(center_xy[1] + half) + 1)
    return y0, y1, x0, x1


def measure(counts, background, flux, weight, center_xy, radius_pix, pixel_arcsec):
    """Aperture numbers from arrays cropped around the centre (centre in crop pixels)."""
    script = io.astroclip_script()
    yy, xx = np.indices(counts.shape)
    aperture = np.hypot(xx - center_xy[0], yy - center_xy[1]) < radius_pix
    covered = aperture & (weight > 0)
    c, b = counts[covered].sum(), background[covered].sum()
    net = c - b
    out = {"net_counts": float(net), "snr": float(net / np.sqrt(max(c, 1.0)))}
    # Point sources on the 3.9" working grid, as in LEMUR's centring.
    factor = max(1, int(round(script.WORK_PIXEL_ARCSEC / pixel_arcsec)))
    binned = script._block_reduce(np.nan_to_num(flux), factor, np.mean)
    exp = script._block_reduce(np.nan_to_num(weight), factor, np.mean)
    ap = script._block_reduce(aperture.astype(float), factor, np.mean) > 0.5
    positive = exp[exp > 0]
    if positive.size == 0:
        out["ps_fraction"] = np.nan
        return out
    mask = exp > script.EXPOSURE_FRACTION * np.percentile(positive, 90)
    sources = script._point_source_mask(binned, mask, pixel_arcsec * factor)
    total = binned[ap & mask].sum()
    out["ps_fraction"] = float(np.clip(binned[ap & mask & sources].sum() / total, 0, 1)) if total > 0 else np.nan
    return out


def measure_lemur(row, cfg):
    from astropy.io import fits
    from astropy.wcs import WCS

    folder = Path(row["folder"])
    counts_path = io._existing(folder / "broad_thresh.img", folder / "broad_thresh.img.gz")
    bkg_path = io._existing(folder / "broad_bkg.img", folder / "broad_bkg.img.gz")
    flux_path, weight_path = io.lemur_files(folder, "broad")
    header = fits.getheader(flux_path)
    wcs = WCS(header).celestial
    pixel_arcsec = io._pixel_arcsec(wcs)
    cx, cy = wcs.wcs_world2pix([[row["center_ra"], row["center_dec"]]], 0)[0]
    radius_arcsec = spatial.field_side_arcsec({"kpc": 2 * APERTURE_KPC}, row["redshift"]) / 2
    half = (radius_arcsec + MARGIN_ARCSEC) / pixel_arcsec
    y0, y1, x0, x1 = _box((cx, cy), half, (header["NAXIS2"], header["NAXIS1"]))
    arrays = [_read_box(p, y0, y1, x0, x1) for p in (counts_path, bkg_path, flux_path, weight_path)]
    return measure(*arrays, (cx - x0, cy - y0), radius_arcsec / pixel_arcsec, pixel_arcsec)


_REF_CACHE = {}


def measure_mock(row, cfg):
    from astropy.io import fits
    from astropy.wcs import WCS

    from .mocks import observe

    obs = Path(row["folder"])
    ref_dir = obs.parents[4] / "reference"
    if ref_dir not in _REF_CACHE:
        _REF_CACHE[ref_dir] = observe.load_reference(ref_dir, "broad")
    bkg_ref, expmap_per_s = _REF_CACHE[ref_dir]
    counts, header = fits.getdata(obs / "broad_counts.fits.gz", header=True)
    flux = fits.getdata(obs / "broad_flux.fits.gz")
    background = float(header["BKGSCAL"]) * bkg_ref
    weight = float(header["EXPOSURE"]) * expmap_per_s
    wcs = WCS(header).celestial
    pixel_arcsec = io._pixel_arcsec(wcs)
    cx, cy = wcs.wcs_world2pix([[row["center_ra"], row["center_dec"]]], 0)[0]
    radius_arcsec = spatial.field_side_arcsec({"kpc": 2 * APERTURE_KPC}, row["redshift"]) / 2
    half = (radius_arcsec + MARGIN_ARCSEC) / pixel_arcsec
    y0, y1, x0, x1 = _box((cx, cy), half, counts.shape)
    crop = [np.asarray(a[y0:y1, x0:x1], dtype=np.float64) for a in (counts, background, flux, weight)]
    return measure(*crop, (cx - x0, cy - y0), radius_arcsec / pixel_arcsec, pixel_arcsec)


def _task(row):
    try:
        out = (measure_lemur if row["source"] == io.LEMUR else measure_mock)(row, None)
        status = "ok"
    except Exception as exc:  # recorded, not fatal
        out, status = {}, f"error: {type(exc).__name__}: {exc}"
    return {"source": row["source"], "name": row["name"], "signal_status": status, **out}


def compute(manifest_path, cache, workers):
    if Path(cache).exists():
        return pd.read_csv(cache)
    df = pd.read_parquet(manifest_path)
    df = df[(df["status"] == "ok") & df["redshift"].notna()]
    rows = df[["source", "name", "folder", "center_ra", "center_dec", "redshift"]].to_dict("records")
    print(f"Measuring {len(rows)} images", flush=True)
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(_task, rows, chunksize=16))
    table = pd.DataFrame(results)
    Path(cache).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(cache, index=False)
    return table


def select(df, signal, snr_min=SNR_MIN, ps_max=PS_MAX):
    """Rows of a manifest-like frame that pass the signal cut (same for all sources)."""
    merged = df.merge(signal[["source", "name", "snr", "ps_fraction"]], on=["source", "name"], how="left")
    keep = (merged["snr"] >= snr_min) & ~(merged["ps_fraction"] > ps_max)
    return df[keep.to_numpy()]


def figure(table, manifest, out, snr_min=SNR_MIN, ps_max=PS_MAX):
    import matplotlib.pyplot as plt

    t = table.merge(manifest[["source", "name", "redshift"]], on=["source", "name"])
    zs = sorted(t.loc[t["source"] != io.LEMUR, "redshift"].unique())
    fig, axes = plt.subplots(2, len(zs), figsize=(4.4 * len(zs), 6.4), squeeze=False)
    colors = {"LEMUR": "k", "TNG300-1": "tab:blue", "TNG-Cluster": "tab:red"}
    for c, z in enumerate(zs):
        near = ((t["source"] == io.LEMUR) & ((t["redshift"] - z).abs() < 0.025)) | (t["redshift"] == z) & (t["source"] != io.LEMUR)
        for source in ["TNG300-1", "TNG-Cluster", "LEMUR"]:
            s = t[near & (t["source"] == source)]
            axes[0, c].hist(np.log10(np.clip(s["snr"], 0.1, None)), np.linspace(-1, 3.5, 46), histtype="step", density=True, color=colors[source], label=f"{source} ({len(s)})")
            axes[1, c].hist(s["ps_fraction"].dropna(), np.linspace(0, 1, 26), histtype="step", density=True, color=colors[source])
        axes[0, c].axvline(np.log10(snr_min), color="gray", ls="--")
        axes[1, c].axvline(ps_max, color="gray", ls="--")
        axes[0, c].set_title(f"z = {z:.2f}", fontsize=9)
        axes[0, c].set_xlabel("log S/N (net counts, r < 250 kpc)")
        axes[1, c].set_xlabel("point-source fraction of aperture flux")
        axes[0, c].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "signal.png", dpi=120)
    plt.close(fig)


def main(argv=None):
    import matplotlib

    matplotlib.use("Agg")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default=str(ROOT / "outputs" / "embeddings" / "harmonized_morphology" / "manifest.parquet"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table = compute(args.manifest, out / "signal.csv", args.workers)
    manifest = pd.read_parquet(args.manifest)
    figure(table, manifest, out)
    print(table["signal_status"].str.slice(0, 60).value_counts().to_string())
    t = table.merge(manifest[["source", "name", "redshift"]], on=["source", "name"])
    for source, s in t.groupby("source"):
        passed = (s["snr"] >= SNR_MIN) & ~(s["ps_fraction"] > PS_MAX)
        print(f"{source}: {passed.sum()} of {len(s)} pass (S/N >= {SNR_MIN:g}, point-source fraction <= {PS_MAX:g})")
    lemur = t[t["source"] == io.LEMUR]
    low = lemur[lemur["snr"] < SNR_MIN].sort_values("snr")
    ps = lemur[lemur["ps_fraction"] > PS_MAX].sort_values("ps_fraction", ascending=False)
    print(f"LEMUR below S/N {SNR_MIN:g} ({len(low)}): " + ", ".join(low["name"].head(25)))
    print(f"LEMUR point-source dominated ({len(ps)}): " + ", ".join(ps["name"].head(25)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
