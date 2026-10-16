"""Chandra ACIS-I observations with SOXS, reduced to LEMUR-like products.

LEMUR images are F = (C - B) / E: counts C, minus blank-sky background B
scaled to the observation's 9-12 keV particle rate, divided by an exposure
map E (cm^2 s) at the band's effective energy. The mocks do the same:

- each observation contains the cluster, the instrumental (particle)
  background, the Galactic foreground and cosmic X-ray background point
  sources (which, as in LEMUR, are not subtracted);
- B comes from one deep (2 Ms) background-only simulation with the particle
  background and foreground, shared by all observations like a blank-sky file
  and scaled by the ratio of 9-12 keV counts. SOXS puts every ACIS-I event on
  one chip and its particle background is uniform, so one scale replaces
  LEMUR's per-chip scales;
- every mock has the same pointing, roll and dither, so the exposure map is the
  same apart from a factor of the exposure time.

The shared background image and the exposure map per second are computed once
per band (``make_reference``) and every image is cropped to the exposed field.
Each observation then stores its counts and flux images; B and E follow from
the references and the header keywords BKGSCAL and EXPOSURE.
"""

import gzip
import json
import shutil
from pathlib import Path

import numpy as np

INSTRUMENT = "chandra_acisi_cy0"
# name: (emin keV, emax keV, effective energy keV), as in LEMUR / CIAO.
BANDS = {"broad": (0.5, 7.0, 2.3), "soft": (0.5, 2.0, 1.25), "hard": (2.0, 7.0, 3.8)}
SCALE_BAND_KEV = (9.0, 12.0)
REFERENCE_BKG_KS = 2000.0
# Blank-sky backgrounds have the detected point sources removed, so they keep
# the cosmic X-ray background (CXB) of fainter sources. Assumed limit of that
# removal (0.5-2 keV, erg cm^-2 s^-1), typical of the 30-100 ks blank-sky fields.
CXB_FLUX_LIMIT = 1e-15


def simulate_observation(simput, evt_file, exp_ks, sky_center, seed):
    import soxs

    soxs.instrument_simulator(
        str(simput),
        str(evt_file),
        (exp_ks, "ks"),
        INSTRUMENT,
        list(sky_center),
        overwrite=True,
        instr_bkgnd=True,
        foreground=True,
        ptsrc_bkgnd=True,
        prng=seed,
    )
    return Path(evt_file)


def _write_gz(path, data, header):
    from astropy.io import fits

    path = Path(path)
    fits.PrimaryHDU(data, header=header).writeto(path, overwrite=True)
    with open(path, "rb") as src, gzip.open(f"{path}.gz", "wb", 6) as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()
    return Path(f"{path}.gz")


def _band_image(events, emin, emax):
    """Counts image of an event file or HDUList in (emin, emax) keV on SOXS's sky grid."""
    import soxs

    hdu = soxs.make_image(events, emin=emin, emax=emax)
    return np.asarray(hdu.data, dtype=np.float64), hdu.header


def _crop(data, header, box):
    """Crop to box = (x0, x1, y0, y1) (0-based, exclusive) and fix the WCS."""
    from astropy.wcs import WCS

    x0, x1, y0, y1 = box
    wcs = WCS(header).celestial[y0:y1, x0:x1]
    out = header.copy()
    for key, value in wcs.to_header().items():
        out[key] = value
    return data[y0:y1, x0:x1], out


def _counts_9_12(evt_file):
    from astropy.io import fits

    energy = fits.getdata(evt_file, "EVENTS")["ENERGY"] / 1000.0
    lo, hi = SCALE_BAND_KEV
    return int(np.sum((energy >= lo) & (energy < hi)))


def make_reference(ref_dir, sky_center, seed):
    """Deep background, exposure map per second and crop box, written once."""
    import soxs
    from astropy.io import fits

    ref_dir = Path(ref_dir)
    meta_file = ref_dir / "reference.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text())
    ref_dir.mkdir(parents=True, exist_ok=True)
    bkg_evt = ref_dir / "background_evt.fits"
    soxs.make_background_file(
        str(bkg_evt),
        (REFERENCE_BKG_KS, "ks"),
        INSTRUMENT,
        list(sky_center),
        overwrite=True,
        foreground=True,
        instr_bkgnd=True,
        ptsrc_bkgnd=False,
        prng=seed,
    )
    bkg_exposure = float(fits.getheader(bkg_evt, "EVENTS")["EXPOSURE"])
    # SOXS exposure maps lack a sky WCS but share the image grid; use the image's.
    _, sky_header = _band_image(str(bkg_evt), *BANDS["broad"][:2])
    box = None
    for band, (emin, emax, energy) in BANDS.items():
        expmap = ref_dir / f"{band}_expmap_full.fits"
        soxs.make_exposure_map(
            str(bkg_evt), str(expmap), energy, normalize=False, overwrite=True
        )
        per_second = fits.getdata(expmap).astype(np.float64) / bkg_exposure
        if per_second.shape != (sky_header["NAXIS2"], sky_header["NAXIS1"]):
            raise ValueError(
                f"exposure map {per_second.shape} is not on the image grid"
            )
        if box is None:  # the exposed field, the same in every band
            ys, xs = np.nonzero(per_second > 0)
            box = (int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1)
        data, hdr = _crop(per_second, sky_header, box)
        hdr.update(
            BUNIT="cm**2",
            EFFENRG=energy,
            BAND=band,
            COMMENT="exposure map per second of exposure",
        )
        _write_gz(ref_dir / f"{band}_expmap_per_s.fits", data.astype(np.float32), hdr)
        expmap.unlink()
        counts, header = _band_image(str(bkg_evt), emin, emax)
        data, hdr = _crop(counts, header, box)
        hdr.update(
            BUNIT="count",
            EXPOSURE=bkg_exposure,
            BAND=band,
            ENERG_LO=emin,
            ENERG_HI=emax,
        )
        _write_gz(ref_dir / f"{band}_bkg_counts.fits", data.astype(np.int32), hdr)
    meta = {
        "instrument": INSTRUMENT,
        "sky_center": list(sky_center),
        "crop_box_x0_x1_y0_y1": list(box),
        "bkg_exposure_s": bkg_exposure,
        "bkg_counts_9_12keV": _counts_9_12(bkg_evt),
        "bands": BANDS,
    }
    with open(bkg_evt, "rb") as src, gzip.open(f"{bkg_evt}.gz", "wb", 6) as dst:
        shutil.copyfileobj(src, dst)
    bkg_evt.unlink()
    meta_file.write_text(json.dumps(meta, indent=1))
    return meta


def make_cxb_reference(ref_dir, sky_center, seed, flux_limit=CXB_FLUX_LIMIT, realizations=20):
    """Add the CXB that blank-sky backgrounds keep to the reference background.

    Every mock observation contains SOXS's whole CXB: point sources down to
    very faint fluxes plus a diffuse unresolved part. LEMUR's blank-sky
    backgrounds contain only the CXB of sources below their detection limit,
    so only that part is subtracted there. This makes the same part for the
    mocks: SOXS's source population (averaged over ``realizations`` draws)
    below ``flux_limit``, plus its diffuse unresolved component, with the
    photons spread uniformly over the field (a blank-sky file averages over
    many fields), observed for the reference exposure. Writes
    {band}_cxb_counts.fits.gz into ``ref_dir`` (atomically) and adds a "cxb"
    entry to reference.json; returns that entry.
    """
    import os
    import tempfile

    import soxs
    from astropy.table import Table
    from soxs.background.point_sources import (
        generate_positions,
        generate_sources,
        make_ptsrc_background,
    )
    from soxs.instrument_registry import instrument_registry
    from soxs.response import AuxiliaryResponseFile
    from soxs.simput import SimputCatalog, SimputPhotonList
    from soxs.utils import get_data_file

    ref_dir = Path(ref_dir)
    meta = json.loads((ref_dir / "reference.json").read_text())
    if "cxb" in meta:
        return meta["cxb"]
    prng = np.random.RandomState(seed)
    spec = instrument_registry[INSTRUMENT]
    fov = 1.5 * spec["fov"]  # arcmin, as SOXS uses for the point-source background
    area = 1.2 * AuxiliaryResponseFile(get_data_file(spec["arf"])).max_area
    draws = [generate_sources(fov, sky_center, prng=prng) for _ in range(realizations)]
    fluxes = np.concatenate([d[2] for d in draws])
    index = np.concatenate([d[3] for d in draws])
    faint = fluxes < flux_limit
    with tempfile.TemporaryDirectory(dir=ref_dir.parent) as tmp:
        tmp = Path(tmp)
        catalog = tmp / "faint_sources.ecsv"
        Table(
            {
                "RA": np.full(faint.sum(), sky_center[0]),
                "Dec": np.full(faint.sum(), sky_center[1]),
                "flux_0.5_2.0_keV": fluxes[faint] / realizations,
                "index": index[faint],
            }
        ).write(catalog, format="ascii.ecsv")
        events = make_ptsrc_background(
            (REFERENCE_BKG_KS, "ks"),
            fov,
            sky_center,
            area=area,
            input_sources=str(catalog),
            diffuse_unresolved=True,
            prng=prng,
        )
        ra, dec = generate_positions(events["energy"].size, fov, sky_center, prng)
        source = SimputPhotonList(ra, dec, events["energy"], events["flux"], name="cxb_faint")
        simput = tmp / "cxb_simput.fits"
        SimputCatalog.from_source(
            str(simput), source, src_filename=str(tmp / "cxb_phlist.fits"), overwrite=True
        )
        evt = tmp / "cxb_evt.fits"
        soxs.instrument_simulator(
            str(simput),
            str(evt),
            (REFERENCE_BKG_KS, "ks"),
            INSTRUMENT,
            list(sky_center),
            overwrite=True,
            instr_bkgnd=False,
            foreground=False,
            ptsrc_bkgnd=False,
            prng=prng,
        )
        box = tuple(meta["crop_box_x0_x1_y0_y1"])
        counts_total = {}
        for band, (emin, emax, _energy) in BANDS.items():
            counts, header = _band_image(str(evt), emin, emax)
            data, hdr = _crop(counts, header, box)
            hdr.update(
                BUNIT="count",
                EXPOSURE=REFERENCE_BKG_KS * 1e3,
                BAND=band,
                CXBLIMIT=flux_limit,
                COMMENT="CXB of sources below CXBLIMIT (0.5-2 keV), spread uniformly",
            )
            _write_gz(tmp / f"{band}_cxb_counts.fits", data.astype(np.int32), hdr)
            counts_total[band] = int(data.sum())
        for band in BANDS:  # rename is atomic: running workers never see partial files
            os.replace(tmp / f"{band}_cxb_counts.fits.gz", ref_dir / f"{band}_cxb_counts.fits.gz")
    cxb = {
        "flux_limit_0.5_2keV_cgs": flux_limit,
        "realizations": realizations,
        "fraction_of_source_flux_below_limit": float(fluxes[faint].sum() / fluxes.sum()),
        "counts_in_reference": counts_total,
    }
    meta["cxb"] = cxb
    tmp_meta = ref_dir / "reference.json.tmp"
    tmp_meta.write_text(json.dumps(meta, indent=1))
    os.replace(tmp_meta, ref_dir / "reference.json")
    return cxb


def load_reference(ref_dir, band, with_cxb=True):
    """(background counts, exposure map per second) for a band, as float arrays.

    The background includes the faint CXB (``make_cxb_reference``) if
    ``with_cxb`` and it has been made.
    """
    from astropy.io import fits

    ref_dir = Path(ref_dir)
    background = fits.getdata(ref_dir / f"{band}_bkg_counts.fits.gz").astype(np.float64)
    cxb = ref_dir / f"{band}_cxb_counts.fits.gz"
    if with_cxb and cxb.exists():
        background += fits.getdata(cxb).astype(np.float64)
    return (
        background,
        fits.getdata(ref_dir / f"{band}_expmap_per_s.fits.gz").astype(np.float64),
    )


def cxb_limit(ref_dir):
    """The CXB flux limit of the reference background, or 0 if it has no CXB."""
    meta = json.loads((Path(ref_dir) / "reference.json").read_text())
    return float(meta.get("cxb", {}).get("flux_limit_0.5_2keV_cgs", 0.0))


def make_products(evt_file, ref_dir, out_dir, meta):
    """Write {band}_counts and {band}_flux (cropped, gzipped) for every band.

    ``meta`` is copied into the headers (e.g. SIM, HALOID, PROJ, REDSHIFT).
    B = BKGSCAL x background reference and E = EXPOSURE x exposure map per
    second (both in ``ref_dir``). Returns per-band summary numbers.
    """
    from astropy.io import fits

    ref = json.loads((Path(ref_dir) / "reference.json").read_text())
    box = tuple(ref["crop_box_x0_x1_y0_y1"])
    limit = float(ref.get("cxb", {}).get("flux_limit_0.5_2keV_cgs", 0.0))
    exposure = float(fits.getheader(evt_file, "EVENTS")["EXPOSURE"])
    n_obs = _counts_9_12(evt_file)
    exposure_ratio = exposure / ref["bkg_exposure_s"]
    scale = n_obs / ref["bkg_counts_9_12keV"] if n_obs >= 20 else exposure_ratio
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "exposure_s": exposure,
        "bkg_scale": scale,
        "exposure_ratio": exposure_ratio,
    }
    for band, (emin, emax, energy) in BANDS.items():
        full, header = _band_image(str(evt_file), emin, emax)
        counts, hdr = _crop(full, header, box)
        bkg_ref, expmap_per_s = load_reference(ref_dir, band, with_cxb=limit > 0)
        background = scale * bkg_ref
        flux = _flux(counts, background, exposure * expmap_per_s)
        hdr.update(dict(meta))
        hdr.update(
            BAND=band,
            ENERG_LO=emin,
            ENERG_HI=emax,
            EFFENRG=energy,
            TELESCOP="CHANDRA",
            INSTRUME="ACIS",
            DETNAM="ACIS-I",
            EXPOSURE=exposure,
            BKGSCAL=scale,
            BKGREF=f"{band}_bkg_counts.fits.gz",
            EXPREF=f"{band}_expmap_per_s.fits.gz",
            CXBLIMIT=(limit, "faint CXB in B below this 0.5-2 keV flux (0: none)"),
        )
        counts_header = hdr.copy()
        counts_header["BUNIT"] = "count"
        _write_gz(
            out_dir / f"{band}_counts.fits", counts.astype(np.int32), counts_header
        )
        flux_header = hdr.copy()
        flux_header.update(BUNIT="/cm**2 /s", BKGSUB=True)
        _write_gz(out_dir / f"{band}_flux.fits", flux.astype(np.float32), flux_header)
        summary[band] = {
            "counts": int(counts.sum()),
            "bkg_counts": round(float(background.sum()), 1),
        }
    return summary


def _flux(counts, background, exposure_map):
    """F = (C - B) / E where E > 0, else 0."""
    flux = np.zeros(np.shape(counts), dtype=np.float64)
    covered = exposure_map > 0
    flux[covered] = (counts[covered] - background[covered]) / exposure_map[covered]
    return flux


def refit_flux(obs_dir, ref_dir):
    """Recompute the flux images of an observation with the current reference.

    For observations made before the reference changed (e.g. before the faint
    CXB was added): F follows from the stored counts and the BKGSCAL and
    EXPOSURE keywords. Returns False if the observation is already current.
    """
    from astropy.io import fits

    obs_dir = Path(obs_dir)
    limit = cxb_limit(ref_dir)
    headers = {b: fits.getheader(obs_dir / f"{b}_flux.fits.gz") for b in BANDS}
    if all(float(h.get("CXBLIMIT", 0.0)) == limit for h in headers.values()):
        return False
    meta_file = obs_dir / "meta.json"
    meta = json.loads(meta_file.read_text())
    for band in BANDS:
        counts = fits.getdata(obs_dir / f"{band}_counts.fits.gz").astype(np.float64)
        header = headers[band]
        bkg_ref, expmap_per_s = load_reference(ref_dir, band, with_cxb=limit > 0)
        background = float(header["BKGSCAL"]) * bkg_ref
        flux = _flux(counts, background, float(header["EXPOSURE"]) * expmap_per_s)
        header["CXBLIMIT"] = (limit, "faint CXB in B below this 0.5-2 keV flux (0: none)")
        tmp = obs_dir / f"{band}_flux.tmp.fits"
        _write_gz(tmp, flux.astype(np.float32), header)
        Path(f"{tmp}.gz").replace(obs_dir / f"{band}_flux.fits.gz")
        meta["products"][band]["bkg_counts"] = round(float(background.sum()), 1)
    meta["products"]["cxb_limit"] = limit
    tmp_meta = obs_dir / "meta.json.tmp"
    tmp_meta.write_text(json.dumps(meta, indent=1, default=str))
    tmp_meta.replace(meta_file)
    return True
