"""Figures and caption numbers for the paper's showcase reductions.

For each object, reads its merged broad_flux.img and writes
paper/figures/showcase_<key>.pdf (smoothed, asinh-stretched image with WCS
axes, a kpc scale bar and the X-ray center) and the macros in
paper/showcase_macros.tex, all taken from the image header and the database
rather than typed by hand:

  \\<key>ObsIDs       ObsIDs actually merged (merge_obs history / OBS_ID)
  \\<key>NObsIDs      how many
  \\<key>ExposureKs   clean exposure in ks (EXPOSURE keyword)
  \\<key>CenterRA/Dec X-ray center (sexagesimal)
  \\<key>Redshift     redshift from the Clusters table
  \\<key>MissingObsIDs ObsIDs in the Obsids table but not in the image ("none")

    python scripts/showcase_figures.py --data-dir /path/to/Chandra \\
        NGC4636=ngcFourSixThreeSix:10 1E0657-56=bullet:6

Each object is NAME=MACROKEY[:FIELD_ARCMIN]; MACROKEY must be letters only.
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline"))
sys.path.insert(0, str(ROOT / "scripts"))
from cluster_paths import resolve_cluster_file  # noqa: E402
from embeddings import stretch_image  # noqa: E402
from paper_stats import merged_obsids  # noqa: E402

DEFAULT_FIELD_ARCMIN = 8.0
SMOOTH_ARCSEC = 1.0  # imaging.create_src_img uses sigma = 2 native pixels


def load_object(db_path, name):
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT ID, redshift FROM Clusters WHERE Name = ?", (name,)
        ).fetchone()
        if row is None:
            raise SystemExit(f"{name} is not in {db_path}")
        obsids = {
            int(r[0])
            for r in con.execute(
                "SELECT DISTINCT Obsid FROM Obsids WHERE ClusterNumber = ?", (row[0],)
            )
        }
        center = con.execute(
            "SELECT center_ra, center_dec, method FROM cluster_center "
            "WHERE ClusterName = ?",
            (name,),
        ).fetchone()
    finally:
        con.close()
    return row[1], obsids, center


def sky_coord(ra, dec):
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    if isinstance(ra, str) and ":" in ra:
        return SkyCoord(ra, str(dec), unit=(u.hourangle, u.deg))
    return SkyCoord(float(ra) * u.deg, float(dec) * u.deg)


def make_figure(image_path, center, redshift, field_arcmin, out_path, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from astropy import units as u
    from astropy.convolution import Gaussian2DKernel, convolve
    from astropy.cosmology import Planck18
    from astropy.io import fits
    from astropy.nddata import Cutout2D
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

    with fits.open(image_path) as hdul:
        data = np.nan_to_num(np.asarray(hdul[0].data, dtype=np.float32))
        wcs = WCS(hdul[0].header).celestial
    pixel_arcsec = float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600.0)
    cut = Cutout2D(
        data,
        center,
        u.Quantity((field_arcmin, field_arcmin), u.arcmin),
        wcs=wcs,
        mode="partial",
        fill_value=0.0,
    )
    sigma = max(SMOOTH_ARCSEC / pixel_arcsec, 0.5)
    image = stretch_image(convolve(cut.data, Gaussian2DKernel(sigma)))

    plt.rcParams.update({"font.size": 9})
    fig = plt.figure(figsize=(3.4, 3.4))
    ax = fig.add_subplot(projection=cut.wcs)
    ax.imshow(image, origin="lower", cmap="magma", vmin=0, vmax=1)
    ax.set_xlabel("RA (J2000)")
    ax.set_ylabel("Dec (J2000)")
    ax.coords[0].set_major_formatter("hh:mm:ss")
    ax.coords[1].set_major_formatter("dd:mm")
    ax.plot(
        center.ra.deg,
        center.dec.deg,
        marker="+",
        color="cyan",
        markersize=9,
        transform=ax.get_transform("icrs"),
    )

    if redshift and redshift > 0:
        # Round scale bar: 100/200/500 kpc, whichever is ~1/4 of the field.
        kpc_per_arcsec = (
            Planck18.kpc_proper_per_arcmin(redshift).to(u.kpc / u.arcsec).value
        )
        target = 0.25 * field_arcmin * 60 * kpc_per_arcsec
        length_kpc = min(
            (10, 20, 50, 100, 200, 500, 1000), key=lambda v: abs(v - target)
        )
        length_pix = length_kpc / kpc_per_arcsec / (pixel_arcsec)
        ny, nx = image.shape
        x0, y0 = 0.06 * nx, 0.07 * ny
        ax.plot([x0, x0 + length_pix], [y0, y0], color="white", lw=1.5)
        ax.text(
            x0 + length_pix / 2,
            y0 + 0.03 * ny,
            f"{length_kpc} kpc",
            color="white",
            ha="center",
            fontsize=8,
        )
    ax.set_title(title, fontsize=9)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def fmt_obsids(obsids):
    return ", ".join(str(o) for o in sorted(obsids)) or "none"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("objects", nargs="+", help="NAME=MACROKEY[:FIELD_ARCMIN]")
    parser.add_argument("--data-dir", required=True, help="':'-separated folders")
    parser.add_argument("--db", default=str(ROOT / "api" / "data" / "lemur.db"))
    parser.add_argument("--out", default=str(ROOT / "paper"))
    args = parser.parse_args(argv)

    out = Path(args.out)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    lines = ["% Generated by scripts/showcase_figures.py -- do not edit by hand."]
    for spec in args.objects:
        name, _, rest = spec.partition("=")
        key, _, field = rest.partition(":")
        if not re.fullmatch(r"[A-Za-z]+", key):
            raise SystemExit(f"Macro key must be letters only: {key!r}")
        field_arcmin = float(field) if field else DEFAULT_FIELD_ARCMIN

        image_path = resolve_cluster_file(args.data_dir, name)
        if image_path is None:
            raise SystemExit(f"No broad_flux.img for {name} in {args.data_dir}")
        from astropy.io import fits

        header = fits.getheader(image_path)
        merged = merged_obsids(header, image_path)
        redshift, catalog_obsids, center_row = load_object(args.db, name)
        if center_row is None:
            raise SystemExit(f"No X-ray center for {name}; run the center step first")
        center = sky_coord(center_row[0], center_row[1])
        exposure_ks = float(header["EXPOSURE"]) / 1e3
        missing = catalog_obsids - merged

        pdf = out / "figures" / f"showcase_{key}.pdf"
        make_figure(image_path, center, redshift, field_arcmin, pdf, name)

        ra = center.ra.to_string(unit="hourangle", sep=":", precision=2, pad=True)
        dec = center.dec.to_string(sep=":", precision=1, alwayssign=True, pad=True)
        macros = {
            "ObsIDs": fmt_obsids(merged),
            "NObsIDs": str(len(merged)),
            "ExposureKs": f"{exposure_ks:.0f}",
            "CenterRA": ra,
            "CenterDec": dec,
            "Redshift": "N/A" if redshift is None else f"{redshift:g}",
            "MissingObsIDs": fmt_obsids(missing),
        }
        lines += [f"\\newcommand{{\\{key}{k}}}{{{v}}}" for k, v in macros.items()]
        print(
            f"{name}: {len(merged)} ObsIDs, {exposure_ks:.0f} ks, center {ra} {dec}"
            f" ({center_row[2]}), missing: {fmt_obsids(missing)} -> {pdf}"
        )
    (out / "showcase_macros.tex").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
