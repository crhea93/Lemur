"""Background subtraction of the LEMUR images: residual (C - B) / B between
4' and 8' from the target, on chips that have a blank-sky background model and
more than 20" from any CSC 2.1 source, for N_OBJECTS objects drawn at random
(fixed seed) among those with at most MAX_OBSIDS ObsIDs observed before 2022.
Also records the fraction of each image's exposed area without a background
model (chips with no blank-sky file are not background subtracted).

    python scripts/validation/validate_background.py OUT_DIR   # writes background.csv
"""

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import csc_sources, eligible_objects, load_image, object_folder  # noqa: E402

N_OBJECTS = 300
MAX_OBSIDS = 3
SEED = 1
ANNULUS_ARCMIN = (4.0, 8.0)
SOURCE_MASK_ARCSEC = 20.0
BLOCK = 64  # native pixels (31.5"); a chip without a blank-sky file has B = 0 in whole blocks


def blocks(a):
    ny, nx = a.shape[0] // BLOCK * BLOCK, a.shape[1] // BLOCK * BLOCK
    return a[:ny, :nx].reshape(ny // BLOCK, BLOCK, nx // BLOCK, BLOCK).sum(axis=(1, 3))


def measure(args):
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

    name, ra, dec = args
    try:
        folder = object_folder(name)
        counts, header = load_image(folder / "broad_thresh.img")
        bkg, _ = load_image(folder / "broad_bkg.img")
        expo, _ = load_image(folder / "broad_thresh.expmap")
        wcs = WCS(header).celestial
        pix = float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600.0)
        exposed = expo > 0.1 * np.percentile(expo[expo > 0], 90)
        full = blocks(exposed.astype(float)) > 0.9 * BLOCK * BLOCK
        modelled = blocks(bkg) > 0
        out = {"name": name, "frac_no_bkg": float((full & ~modelled).sum() / max(full.sum(), 1))}
        has_model = np.zeros_like(exposed)
        expanded = np.kron(modelled, np.ones((BLOCK, BLOCK), bool))
        has_model[: expanded.shape[0], : expanded.shape[1]] = expanded
        tx, ty = wcs.all_world2pix([[ra, dec]], 0)[0]
        yy, xx = np.indices(counts.shape)
        rr = np.hypot(xx - tx, yy - ty) * pix / 60
        region = exposed & has_model & (rr >= ANNULUS_ARCMIN[0]) & (rr <= ANNULUS_ARCMIN[1])
        src = csc_sources(ra, dec, ANNULUS_ARCMIN[1] + 1, ["name", "ra", "dec"])
        if src is not None and len(src):
            sx, sy = wcs.all_world2pix(src[["ra", "dec"]].to_numpy(float), 0).T
            for x, y in zip(sx, sy):
                region &= np.hypot(xx - x, yy - y) * pix > SOURCE_MASK_ARCSEC
        if region.sum() > 1000:
            c, b = counts[region].sum(), bkg[region].sum()
            out.update(bkg_C=float(c), bkg_B=float(b), bkg_resid=float((c - b) / b))
        return out
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "error": repr(exc)[:200]}


def main(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    objs = eligible_objects(MAX_OBSIDS)
    objs = objs.sample(min(N_OBJECTS, len(objs)), random_state=SEED)
    args = [(name, float(r.ra), float(r.dec)) for name, r in objs.iterrows()]
    with ProcessPoolExecutor(3) as pool:
        rows = list(pool.map(measure, args))
    pd.DataFrame(rows).to_csv(out_dir / "background.csv", index=False)
    print(f"wrote {out_dir / 'background.csv'} ({len(rows)} objects)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "paper/validation")
