"""Read LEMUR images and the regenerated TNG mocks into one record type.

Both sides provide, per band, the background-subtracted flux image
F = (C - B) / E (photons cm^-2 s^-1 per pixel) and a broad-band exposure map.
LEMUR keeps an exposure map only for the broad band, so the broad map serves
as the weight of every band on both sides (``spatial.extract``).

Centres:

- LEMUR: the catalog X-ray centre (``cluster_center`` table), which LEMUR
  computed with ``find_xray_peak`` on the broad flux and exposure map.
- Mocks: the same ``find_xray_peak`` on the mock's broad flux and exposure
  map, with the halo position as the prior (as LEMUR uses the target position),
  or the halo position itself (``center: halo``).
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/home/crhea/Projects/Lemur/api/data/lemur.db")
DEFAULT_DATA = Path("/run/media/crhea/ef10789c-0ada-41e4-8d3f-8f17dbcc0558")
DEFAULT_MOCKS = DEFAULT_DATA / "_domain_gap" / "mocks"
BANDS = ("broad", "soft", "hard")
LEMUR = "LEMUR"


@dataclass
class Image:
    source: str  # LEMUR, TNG300-1 or TNG-Cluster
    name: str  # LEMUR object, or {halo}_{proj}_z{z}_{exp}ks for a mock
    band: str
    flux: np.ndarray  # F per pixel, photons cm^-2 s^-1 (may be a memmap)
    weight: np.ndarray  # broad exposure map, cm^2 s; 0 where not covered
    wcs: object  # celestial astropy WCS of both arrays
    pixel_arcsec: float
    redshift: float | None
    exposure_ks: float
    center_radec: tuple | None  # None: find the X-ray peak (mocks)
    prior_radec: tuple | None = None
    meta: dict = field(default_factory=dict)


def astroclip_script():
    """LEMUR's scripts/astroclip_xray_similarity.py (centring and AstroCLIP)."""
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    import astroclip_xray_similarity

    return astroclip_xray_similarity


def _read(path):
    """Primary image and header; uncompressed files stay memory-mapped."""
    from astropy.io import fits

    hdul = fits.open(path, memmap=True)
    return hdul[0].data, hdul[0].header


def _pixel_arcsec(wcs):
    from astropy.wcs.utils import proj_plane_pixel_scales

    return float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600.0)


def _existing(*paths):
    for path in paths:
        if Path(path).exists():
            return Path(path)
    return None


# ---------------------------------------------------------------- LEMUR


def lemur_catalog(db_path=DEFAULT_DB, clusters_only=True):
    """LEMUR objects with redshift, X-ray centre and observation summary."""
    from .audit_lemur import load_catalog

    catalog = load_catalog(db_path)
    if clusters_only:
        catalog = catalog[catalog["is_cluster"]]
    return catalog.sort_values("Name").reset_index(drop=True)


def lemur_files(folder, band):
    """(flux, broad exposure map) paths of a LEMUR folder, or None if missing."""
    folder = Path(folder)
    if band == "broad":
        flux = _existing(folder / "broad_flux.img", folder / "broad_flux.img.gz")
    else:
        flux = _existing(
            folder / "bands" / f"{band}_flux.img",
            folder / "bands" / f"{band}_flux.img.gz",
        )
    weight = _existing(
        folder / "broad_thresh.expmap", folder / "broad_thresh.expmap.gz"
    )
    return None if flux is None or weight is None else (flux, weight)


def load_lemur(row, band, data_dir=DEFAULT_DATA):
    """Image of one ``lemur_catalog`` row, or None if its files are missing."""
    from astropy.wcs import WCS

    from .audit_lemur import resolve_folder

    folder = resolve_folder(data_dir, row["Name"])
    files = None if folder is None else lemur_files(folder, band)
    if files is None:
        return None
    flux, header = _read(files[0])
    weight, _ = _read(files[1])
    wcs = WCS(header).celestial
    ra, dec, z = _number(row.get("center_ra")), _number(row.get("center_dec")), _number(row.get("redshift"))
    return Image(
        source=LEMUR,
        name=row["Name"],
        band=band,
        flux=flux,
        weight=weight,
        wcs=wcs,
        pixel_arcsec=_pixel_arcsec(wcs),
        redshift=z if z is not None and z > 0 else None,
        exposure_ks=float(header.get("EXPOSURE", 0.0)) / 1e3,
        center_radec=None if ra is None or dec is None else (ra, dec),
        meta={
            "n_obsids": int(_number(row.get("n_obsids")) or 0),
            "n_acis_i": int(_number(row.get("n_acis_i")) or 0),
            "n_acis_s": int(_number(row.get("n_acis_s")) or 0),
            "folder": str(folder),
        },
    )


def _number(value):
    """float(value), or None for None/NaN."""
    if value is None:
        return None
    value = float(value)
    return None if np.isnan(value) else value


# ---------------------------------------------------------------- mocks


def mock_observations(root=DEFAULT_MOCKS, sims=None, redshifts=None, exposures=None, projections=None):
    """Finished mock observation directories, sorted, optionally filtered."""
    root = Path(root)
    found = []
    for meta_file in sorted(root.glob("*/*/z*/*/*ks/meta.json")):
        obs = meta_file.parent
        sim, halo, ztag, proj, etag = obs.parts[-5:]
        z, exp = float(ztag[1:]), float(etag[:-2])
        if sims and sim not in sims:
            continue
        if redshifts and not any(abs(z - r) < 1e-6 for r in redshifts):
            continue
        if exposures and not any(abs(exp - e) < 1e-6 for e in exposures):
            continue
        if projections and proj not in projections:
            continue
        if all((obs / f"{band}_flux.fits.gz").exists() for band in BANDS):
            found.append(obs)
    return found


def mock_name(obs_dir):
    sim, halo, ztag, proj, etag = Path(obs_dir).parts[-5:]
    return sim, f"{halo}_{proj}_{ztag}_{etag}"


def load_mock(obs_dir, band, reference_dir=None):
    """Image of one mock observation directory."""
    from astropy.io import fits
    from astropy.wcs import WCS

    obs_dir = Path(obs_dir)
    reference_dir = Path(reference_dir or obs_dir.parents[4] / "reference")
    ref = json.loads((reference_dir / "reference.json").read_text())
    with fits.open(obs_dir / f"{band}_flux.fits.gz") as hdul:
        flux = np.asarray(hdul[0].data, dtype=np.float32)
        header = hdul[0].header
    expmap_per_s = fits.getdata(reference_dir / "broad_expmap_per_s.fits.gz")
    weight = (float(header["EXPOSURE"]) * expmap_per_s).astype(np.float32)
    meta = json.loads((obs_dir / "meta.json").read_text())
    wcs = WCS(header).celestial
    sim, name = mock_name(obs_dir)
    halo = meta.get("halo", {})
    h = 0.6774
    return Image(
        source=sim,
        name=name,
        band=band,
        flux=flux,
        weight=weight,
        wcs=wcs,
        pixel_arcsec=_pixel_arcsec(wcs),
        redshift=float(meta["redshift"]),
        exposure_ks=float(header["EXPOSURE"]) / 1e3,
        center_radec=None,
        prior_radec=tuple(ref["sky_center"]),
        meta={
            "halo_id": int(meta["halo_id"]),
            "projection": meta["projection"],
            "M500c_Msun": float(halo["Group_M_Crit500"]) * 1e10 / h
            if "Group_M_Crit500" in halo
            else None,
            "R500c_kpc": float(halo["Group_R_Crit500"]) / h
            if "Group_R_Crit500" in halo
            else None,
            "folder": str(obs_dir),
        },
    )


def peak_center(broad):
    """(ra, dec) of the X-ray peak of a broad-band Image, found as LEMUR finds
    its centres (``find_xray_peak`` with the prior position); the prior if no
    peak is found."""
    prior = tuple(
        float(v) for v in broad.wcs.wcs_world2pix([broad.prior_radec], 0)[0]
    )
    peak = astroclip_script().find_xray_peak(
        broad.flux, broad.weight, broad.pixel_arcsec, prior_xy=prior
    )
    if peak is None:
        return broad.prior_radec
    ra, dec = broad.wcs.wcs_pix2world([peak], 0)[0]
    return float(ra), float(dec)
