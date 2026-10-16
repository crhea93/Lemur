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


def load_reference(ref_dir, band):
    """(background counts, exposure map per second) for a band, as float arrays."""
    from astropy.io import fits

    ref_dir = Path(ref_dir)
    return (
        fits.getdata(ref_dir / f"{band}_bkg_counts.fits.gz").astype(np.float64),
        fits.getdata(ref_dir / f"{band}_expmap_per_s.fits.gz").astype(np.float64),
    )


def make_products(evt_file, ref_dir, out_dir, meta):
    """Write {band}_counts and {band}_flux (cropped, gzipped) for every band.

    ``meta`` is copied into the headers (e.g. SIM, HALOID, PROJ, REDSHIFT).
    B = BKGSCAL x background reference and E = EXPOSURE x exposure map per
    second (both in ``ref_dir``). Returns per-band summary numbers.
    """
    from astropy.io import fits

    ref = json.loads((Path(ref_dir) / "reference.json").read_text())
    box = tuple(ref["crop_box_x0_x1_y0_y1"])
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
        bkg_ref, expmap_per_s = load_reference(ref_dir, band)
        background = scale * bkg_ref
        exposure_map = exposure * expmap_per_s
        flux = np.zeros_like(counts)
        covered = exposure_map > 0
        flux[covered] = (counts[covered] - background[covered]) / exposure_map[covered]
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
