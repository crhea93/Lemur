from pathlib import Path

import numpy as np

# Working resolution for peak finding; matches an 8x-binned ACIS image.
WORK_PIXEL_ARCSEC = 3.936
# Band-pass scales: cluster-core scale minus a large-scale background, so
# uniformly bright chips (e.g. back-illuminated S3) and point sources don't win.
CORE_SIGMA_ARCSEC = 30.0
BACKGROUND_SIGMA_ARCSEC = 120.0
REFINE_SIGMA_ARCSEC = 8.0
REFINE_RADIUS_ARCSEC = 45.0
# Point-source suppression: compact excess of the small-scale over the local
# smoothing, flagged at POINT_SOURCE_NSIGMA robust sigmas and masked out.
POINT_SOURCE_SIGMA_ARCSEC = 4.0
LOCAL_SIGMA_ARCSEC = 20.0
POINT_SOURCE_NSIGMA = 5.0
POINT_SOURCE_DILATE_ARCSEC = 8.0
# Catalog prior: prefer the peak within PRIOR_RADIUS_ARCSEC of the catalog
# position unless the best peak on the whole array is GLOBAL_OVERRIDE times
# stronger (catalog positions are sometimes several arcminutes off).
PRIOR_RADIUS_ARCSEC = 240.0
GLOBAL_OVERRIDE = 2.0
# Distance from the chip/exposure edge excluded from the peak search.
EDGE_ARCSEC = 30.0
# Pixels with exposure below this fraction of the typical exposure are masked.
EXPOSURE_FRACTION = 0.1


def _block_reduce(array, factor, func):
    if factor <= 1:
        return array
    ny, nx = (array.shape[0] // factor) * factor, (array.shape[1] // factor) * factor
    trimmed = array[:ny, :nx]
    return func(
        trimmed.reshape(ny // factor, factor, nx // factor, factor), axis=(1, 3)
    )


def _masked_smooth(data, mask, sigma_pix):
    """Mask-aware Gaussian smoothing, so chip edges are not darkened."""
    from scipy.ndimage import gaussian_filter

    weights = gaussian_filter(mask.astype(np.float64), sigma_pix)
    smoothed = gaussian_filter(np.where(mask, data, 0.0), sigma_pix)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = smoothed / weights
    out[weights < 1e-3] = 0.0
    return out


def _point_source_mask(binned, mask, work_arcsec):
    from scipy.ndimage import binary_dilation

    small = _masked_smooth(binned, mask, POINT_SOURCE_SIGMA_ARCSEC / work_arcsec)
    local = _masked_smooth(binned, mask, LOCAL_SIGMA_ARCSEC / work_arcsec)
    excess = small - local
    values = excess[mask]
    if values.size == 0:
        return np.zeros_like(mask)
    median = np.median(values)
    sigma = 1.4826 * np.median(np.abs(values - median))
    if sigma <= 0:
        return np.zeros_like(mask)
    sources = (excess > median + POINT_SOURCE_NSIGMA * sigma) & (small > 2.0 * local)
    iterations = max(1, int(round(POINT_SOURCE_DILATE_ARCSEC / work_arcsec)))
    return binary_dilation(sources, iterations=iterations) & mask


def find_xray_peak(data, exposure=None, pixel_arcsec=0.492, prior_xy=None):
    """Locate the cluster emission peak in a flux image.

    :param data: 2D flux image (e.g. broad_flux.img)
    :param exposure: optional exposure map on the same pixel grid
    :param pixel_arcsec: pixel size of ``data`` in arcseconds
    :param prior_xy: optional catalog position, 0-based pixels of ``data``
    :return: (x, y) peak in 0-based pixel coordinates of ``data``, or None
    """
    from scipy.ndimage import binary_erosion, label

    data = np.nan_to_num(np.asarray(data, dtype=np.float64), nan=0.0)
    factor = max(1, int(round(WORK_PIXEL_ARCSEC / pixel_arcsec)))
    work_arcsec = pixel_arcsec * factor
    binned = _block_reduce(data, factor, np.mean)

    if exposure is not None and np.shape(exposure) == data.shape:
        exp = _block_reduce(
            np.nan_to_num(np.asarray(exposure, dtype=np.float64)), factor, np.mean
        )
        positive = exp[exp > 0]
        if positive.size == 0:
            return None
        mask = exp > EXPOSURE_FRACTION * np.percentile(positive, 90)
    else:
        # Without an exposure map, treat regions with any counts nearby as covered.
        mask = (
            _masked_smooth((binned > 0).astype(float), np.ones_like(binned, bool), 2.0)
            > 0.05
        )

    covered = binary_erosion(mask, iterations=max(1, int(EDGE_ARCSEC / work_arcsec)))
    if not covered.any():
        covered = mask
    if not covered.any():
        return None
    # The global search uses only the largest contiguous exposed region (the
    # aimpoint array), so detached off-axis chips with higher background can't win.
    search = covered
    labels, count = label(covered)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        search = labels == np.argmax(sizes)

    # Smooth only over covered pixels that are not point sources.
    weights = mask & ~_point_source_mask(binned, mask, work_arcsec)
    band_pass = _masked_smooth(
        binned, weights, CORE_SIGMA_ARCSEC / work_arcsec
    ) - _masked_smooth(binned, weights, BACKGROUND_SIGMA_ARCSEC / work_arcsec)
    global_map = np.where(search, band_pass, -np.inf)
    by, bx = np.unravel_index(np.argmax(global_map), global_map.shape)

    if prior_xy is not None:
        yy, xx = np.indices(band_pass.shape)
        px = (prior_xy[0] + 0.5) / factor - 0.5
        py = (prior_xy[1] + 0.5) / factor - 0.5
        near = covered & (
            (xx - px) ** 2 + (yy - py) ** 2 <= (PRIOR_RADIUS_ARCSEC / work_arcsec) ** 2
        )
        if near.any():
            local_map = np.where(near, band_pass, -np.inf)
            ly, lx = np.unravel_index(np.argmax(local_map), local_map.shape)
            local_value = band_pass[ly, lx]
            if local_value > 0 and band_pass[by, bx] <= GLOBAL_OVERRIDE * local_value:
                by, bx = ly, lx

    # Refine on a finer smoothing scale within a small radius of the coarse peak.
    fine = _masked_smooth(binned, weights, REFINE_SIGMA_ARCSEC / work_arcsec)
    yy, xx = np.indices(fine.shape)
    radius = REFINE_RADIUS_ARCSEC / work_arcsec
    fine[((xx - bx) ** 2 + (yy - by) ** 2 > radius**2) | ~mask] = -np.inf
    by, bx = np.unravel_index(np.argmax(fine), fine.shape)

    # Center of the binned pixel in native 0-based pixel coordinates.
    return (bx + 0.5) * factor - 0.5, (by + 0.5) * factor - 0.5


def _prior_pixel(wcs, ra, dec):
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    if ra is None or dec is None:
        return None
    try:
        if isinstance(ra, str) and ":" in ra:
            coord = SkyCoord(ra, str(dec), unit=(u.hourangle, u.deg))
        else:
            coord = SkyCoord(float(ra) * u.deg, float(dec) * u.deg)
    except (TypeError, ValueError):
        return None
    x, y = wcs.world_to_pixel(coord)
    return float(x), float(y)


def _xray_center(image_path, prior_ra=None, prior_dec=None):
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

    with fits.open(image_path) as hdul:
        data = hdul[0].data
        wcs = WCS(hdul[0].header).celestial
    pixel_arcsec = float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600.0)

    exposure = None
    expmap_path = Path(image_path).with_name("broad_thresh.expmap")
    if expmap_path.exists():
        with fits.open(expmap_path) as hdul:
            exposure = hdul[0].data

    prior_xy = _prior_pixel(wcs, prior_ra, prior_dec)
    peak = find_xray_peak(data, exposure, pixel_arcsec, prior_xy=prior_xy)
    if peak is None:
        return None
    x, y = peak
    sky = wcs.pixel_to_world(x, y)
    return float(sky.icrs.ra.deg), float(sky.icrs.dec.deg), float(x), float(y)


def compute_center(
    cluster_name,
    image_path,
    initial_ra,
    initial_dec,
    db_service,
    fallback_ra=None,
    fallback_dec=None,
):
    """Compute and store the canonical cluster center.

    Uses the X-ray emission peak of ``image_path`` (see ``find_xray_peak``);
    center_x/center_y are 0-based pixel coordinates in that image. Falls back
    to the provided RA/DEC when the image cannot be used.
    """
    prior_ra = initial_ra if initial_ra is not None else fallback_ra
    prior_dec = initial_dec if initial_dec is not None else fallback_dec
    result = None
    try:
        result = _xray_center(image_path, prior_ra, prior_dec)
    except Exception as exc:
        print(f"  X-ray center failed for {cluster_name}: {exc}")

    if result is not None:
        center_ra, center_dec, center_x, center_y = result
        method = "xray_bandpass_peak"
    else:
        center_ra = initial_ra if initial_ra is not None else fallback_ra
        center_dec = initial_dec if initial_dec is not None else fallback_dec
        center_x = center_y = None
        method = "placeholder_existing_centroid"
    if center_ra is None or center_dec is None:
        raise RuntimeError(
            f"Unable to compute center for {cluster_name}: no valid RA/DEC available."
        )

    db_service.upsert_center(
        cluster_name,
        center_ra=center_ra,
        center_dec=center_dec,
        center_x=center_x,
        center_y=center_y,
        method=method,
        image_path=str(Path(image_path)),
    )
    return db_service.get_center(cluster_name)
