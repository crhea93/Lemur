"""Flux scale of the LEMUR images against the Chandra Source Catalog 2.1.

Stage 1 (catalog only): for every object whose ObsIDs all started before 2022
and that has at most MAX_OBSIDS ObsIDs, find bright (significance > 10),
isolated (no other CSC source within 30"), point-like, non-variable,
unconfused, unsaturated, not piled-up CSC sources within 3' of the target.
Stage 2 (images): aperture photometry of those sources on the LEMUR broad,
soft and hard flux images F = (C - B) / E (8" aperture, local level from a
15-30" annulus), next to the CSC aperture-corrected photon fluxes in the same
bands: b (0.5-7 keV), s + m (0.5-2 keV) and h (2-7 keV).

    python scripts/validation/validate_flux.py OUT_DIR   # writes flux_sources.csv
"""

import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CSC_FLAGS, csc_sources, eligible_objects, load_image, object_folder  # noqa: E402

MAX_OBSIDS = 5
SEARCH_ARCMIN = 3.0
APERTURE_ARCSEC = 8.0
ANNULUS_ARCSEC = (15.0, 30.0)
ISOLATION_ARCSEC = 30.0
BANDS = {
    "broad": ("broad_flux.img", ["photflux_aper_b"]),
    "soft": ("bands/soft_flux.img", ["photflux_aper_s", "photflux_aper_m"]),
    "hard": ("bands/hard_flux.img", ["photflux_aper_h"]),
}
COLUMNS = (
    ["name", "ra", "dec", "significance", "hard_hs", "hard_ms", *CSC_FLAGS]
    + [c for _, cols in BANDS.values() for c in cols]
    + ["photflux_aper_lolim_b", "photflux_aper_hilim_b"]
)


def good_sources(item):
    name, ra, dec = item
    src = csc_sources(ra, dec, SEARCH_ARCMIN + ISOLATION_ARCSEC / 60, COLUMNS)
    if src is None or src.empty:
        return name, None
    cosd = np.cos(np.radians(dec))
    src["sep_arcmin"] = np.hypot((src.ra - ra) * cosd, src.dec - dec) * 60
    good = (
        (src.sep_arcmin <= SEARCH_ARCMIN)
        & (src.significance > 10)
        & src.photflux_aper_b.notna()
        & ~src.name.str.strip().str.endswith("X")
    )
    for flag in CSC_FLAGS:
        good &= ~src[flag].fillna(False).astype(bool)
    keep = []
    for i, s in src[good].iterrows():
        d = np.hypot((src.ra - s.ra) * cosd, src.dec - s.dec) * 3600
        if not (d[src.index != i] < ISOLATION_ARCSEC).any():
            keep.append(s)
    return name, (pd.DataFrame(keep) if keep else None)


def photometry(args):
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

    name, src = args
    try:
        folder = object_folder(name)
        expo, header = load_image(folder / "broad_thresh.expmap")
        wcs = WCS(header).celestial
        pix = float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600.0)
        exposed = expo > 0.1 * np.percentile(expo[expo > 0], 90)
        sx, sy = wcs.all_world2pix(src[["ra", "dec"]].to_numpy(float), 0).T
        r_ap, r_in, r_out = (a / pix for a in (APERTURE_ARCSEC, *ANNULUS_ARCSEC))
        rows = [
            dict(object=name, source=s["name"].strip(), sep_arcmin=s.sep_arcmin,
                 hard_hs=s.hard_hs, hard_ms=s.hard_ms,
                 csc_lo_b=s.photflux_aper_lolim_b, csc_hi_b=s.photflux_aper_hilim_b)
            for _, s in src.iterrows()
        ]
        for band, (filename, cols) in BANDS.items():
            flux, _ = load_image(folder / filename)
            if flux.shape != expo.shape:
                continue
            for row, (_, s), x, y in zip(rows, src.iterrows(), sx, sy):
                x0, y0, h = int(round(x)), int(round(y)), int(np.ceil(r_out)) + 2
                ys, xs = slice(max(y0 - h, 0), y0 + h + 1), slice(max(x0 - h, 0), x0 + h + 1)
                yy, xx = np.mgrid[ys, xs]
                rr = np.hypot(xx - x, yy - y)
                ap, ann = rr <= r_ap, (rr >= r_in) & (rr <= r_out)
                ok = exposed[ys, xs]
                if ap.sum() == 0 or not ok[ap].all() or ok[ann].mean() < 0.8:
                    row["edge"] = True
                    continue
                f = flux[ys, xs]
                local = f[ann & ok].mean() * ap.sum()
                row[f"lemur_{band}"] = f[ap].sum() - local
                row[f"local_frac_{band}"] = local / max(abs(f[ap].sum()), 1e-30)
                csc = [s[c] for c in cols]
                row[f"csc_{band}"] = np.nan if any(pd.isna(v) for v in csc) else float(sum(csc))
        return rows
    except Exception as exc:  # noqa: BLE001
        return [dict(object=name, error=repr(exc)[:200])]


def main(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    objs = eligible_objects(MAX_OBSIDS)
    items = [(name, float(r.ra), float(r.dec)) for name, r in objs.iterrows()]
    print(f"stage 1: {len(items)} eligible objects", flush=True)
    found = []
    with ThreadPoolExecutor(4) as pool:
        for i, (name, src) in enumerate(pool.map(good_sources, items)):
            if src is not None:
                found.append((name, src))
            if i % 200 == 0:
                print(f"  {i} queried, {len(found)} with sources", flush=True)
    print(f"stage 2: photometry of {sum(len(s) for _, s in found)} sources in {len(found)} objects", flush=True)
    rows = []
    with ProcessPoolExecutor(3) as pool:
        for r in pool.map(photometry, found):
            rows.extend(r)
    pd.DataFrame(rows).to_csv(out_dir / "flux_sources.csv", index=False)
    print(f"wrote {out_dir / 'flux_sources.csv'}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "paper/validation")
