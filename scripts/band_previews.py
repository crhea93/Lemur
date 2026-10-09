"""Website previews of each object's broad, soft and hard band images.

For every object in the catalog database, renders the background-subtracted
images to Web/Cluster_plots/<name>/:

    bkgsub_exp.png   broad band (0.5-7 keV), <folder>/broad_flux.img
    soft_exp.png     soft band (0.5-2 keV), <folder>/bands/soft_flux.img.gz
    hard_exp.png     hard band (2-7 keV), <folder>/bands/hard_flux.img.gz

in the style of Pipeline/imaging.py (Gaussian smoothing, asinh stretch, magma,
WCS axes). The three bands of an object share one display range per band,
not across bands. Existing previews are kept unless --redo.

    python scripts/band_previews.py --data-dir DIR [--redo] [NAME ...]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.convolution import Gaussian2DKernel, convolve  # noqa: E402
from astropy.io import fits  # noqa: E402
from astropy.visualization import AsinhStretch, ImageNormalize  # noqa: E402
from astropy.wcs import WCS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline"))
from cluster_paths import resolve_cluster_file  # noqa: E402

PLOTS_DIR = ROOT / "Web" / "Cluster_plots"
# preview file -> image relative to the object's data folder
BANDS = {
    "bkgsub_exp.png": "broad_flux.img",
    "soft_exp.png": "bands/soft_flux.img.gz",
    "hard_exp.png": "bands/hard_flux.img.gz",
}
MAX_PIXELS = 2048  # bin larger images down for the preview


def render(image_path, out_path):
    with fits.open(image_path) as hdul:
        data = np.nan_to_num(hdul[0].data.astype(np.float64))
        wcs = WCS(hdul[0].header)
    factor = int(np.ceil(max(data.shape) / MAX_PIXELS))
    if factor > 1:
        ny, nx = (s // factor * factor for s in data.shape)
        data = data[:ny, :nx].reshape(ny // factor, factor, nx // factor, factor).mean(
            axis=(1, 3)
        )
        wcs = wcs.slice((slice(None, None, factor), slice(None, None, factor)))
    smoothed = convolve(data, Gaussian2DKernel(x_stddev=2))
    positive = smoothed[np.isfinite(smoothed) & (smoothed > 0)]
    vmin, vmax = (0.0, 1.0)
    if positive.size:
        vmin, vmax = np.percentile(positive, [5.0, 99.7])
        if vmax <= vmin:
            vmin, vmax = positive.min(), positive.max()
    norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch(a=0.08), clip=True)
    fig = plt.figure()
    ax = fig.add_subplot(projection=wcs)
    ax.imshow(np.nan_to_num(smoothed, nan=0.0), cmap="magma", norm=norm, origin="lower")
    ax.set_xlabel("RA J2000")
    ax.set_ylabel("DEC J2000")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--db", default=str(ROOT / "api/data/lemur.db"))
    parser.add_argument("--redo", action="store_true", help="Redraw existing previews")
    parser.add_argument("names", nargs="*", help="Only these objects")
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.db)
    names = args.names or [n for (n,) in con.execute("SELECT Name FROM Clusters ORDER BY Name")]
    con.close()
    made = missing = failed = 0
    for name in names:
        broad = resolve_cluster_file(args.data_dir, name, "broad_flux.img")
        if broad is None:
            missing += 1
            continue
        for preview, relative in BANDS.items():
            out_path = PLOTS_DIR / name / preview
            image_path = broad.parent / relative
            if not image_path.exists() or (out_path.exists() and not args.redo):
                continue
            try:
                render(image_path, out_path)
                made += 1
            except Exception as exc:
                failed += 1
                print(f"{name} {preview}: {exc}", flush=True)
    print(f"Previews made {made}; failed {failed}; objects without images {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
