"""Fields of view, area-weighted resampling and coverage.

A field is a square centred on the object's centre, either physical
(``{"kpc": 500}``, needs a redshift) or angular (``{"arcsec": 251.9}``,
``{"arcmin": 4.2}`` or ``{"native_pixels": 512}`` of 0.492").

``extract`` maps a field onto a ``grid`` x ``grid`` output by exact pixel
overlap (no interpolation). Each output pixel is the exposure-weighted mean of
the flux images F = (C - B) / E it covers:

    sum(F * E) / sum(E)  ( = sum(C - B) / sum(E) when E is the band's own map),

divided by the native pixel area, so values are surface brightness in
photons cm^-2 s^-1 arcsec^-2 whatever the input binning. ``coverage`` is the
fraction of each output pixel that is on the image with E > 0.

Both LEMUR and SOXS images are north-up tangent-plane grids, so the overlap
is separable in x and y.
"""

import numpy as np

ACIS_PIXEL_ARCSEC = 0.492


def cosmology(name="Planck15"):
    """An astropy cosmology by name. Planck15 is the TNG cosmology."""
    import astropy.cosmology

    return getattr(astropy.cosmology, name)


def field_side_arcsec(field, redshift=None, cosmo=None):
    """Side of a square field in arcsec, or None if it needs a missing redshift."""
    if "kpc" in field:
        if redshift is None or not redshift > 0:
            return None
        from astropy import units as u

        cosmo = cosmo or cosmology()
        kpc_per_arcsec = cosmo.kpc_proper_per_arcmin(redshift).to(u.kpc / u.arcsec).value
        return float(field["kpc"]) / float(kpc_per_arcsec)
    if "arcsec" in field:
        return float(field["arcsec"])
    if "arcmin" in field:
        return 60.0 * float(field["arcmin"])
    if "native_pixels" in field:
        return float(field["native_pixels"]) * ACIS_PIXEL_ARCSEC
    raise ValueError(f"unknown field {field}")


def overlap_matrix(start, side, n_out, first_pixel, n_in):
    """(n_out, n_in) fraction of each output pixel covered by each input pixel.

    Output pixel k spans [start + k * side / n_out, start + (k + 1) * side / n_out)
    in 0-based input pixel coordinates (pixel i spans [i - 0.5, i + 0.5)); the
    input pixels are first_pixel ... first_pixel + n_in - 1.
    """
    step = side / n_out
    lo_out = start + step * np.arange(n_out)
    centers = first_pixel + np.arange(n_in)
    lo = np.maximum(lo_out[:, None], centers[None, :] - 0.5)
    hi = np.minimum(lo_out[:, None] + step, centers[None, :] + 0.5)
    return (np.clip(hi - lo, 0.0, None) / step).astype(np.float64)


def extract(flux, weight, center_xy, side_pix, grid, pixel_arcsec, weighted=True):
    """(surface brightness, coverage) on a grid x grid field.

    ``center_xy`` is the field centre in 0-based pixels of ``flux`` and
    ``side_pix`` its side in those pixels. Only the overlapping part of the
    (possibly memory-mapped) inputs is read. ``weighted=False`` takes the
    plain area mean of F, uncovered pixels counting as 0 (LEMUR's AstroCLIP
    baseline).
    """
    ny, nx = flux.shape
    x0 = center_xy[0] - side_pix / 2.0
    y0 = center_xy[1] - side_pix / 2.0
    ix0, ix1 = max(0, int(np.floor(x0 + 0.5))), min(nx, int(np.ceil(x0 + side_pix + 0.5)))
    iy0, iy1 = max(0, int(np.floor(y0 + 0.5))), min(ny, int(np.ceil(y0 + side_pix + 0.5)))
    if ix1 <= ix0 or iy1 <= iy0:
        zeros = np.zeros((grid, grid), np.float32)
        return zeros, zeros.copy()
    f = np.nan_to_num(np.asarray(flux[iy0:iy1, ix0:ix1], dtype=np.float64))
    w = np.nan_to_num(np.asarray(weight[iy0:iy1, ix0:ix1], dtype=np.float64))
    w[w < 0] = 0.0
    ox = overlap_matrix(x0, side_pix, grid, ix0, ix1 - ix0)
    oy = overlap_matrix(y0, side_pix, grid, iy0, iy1 - iy0)
    coverage = oy @ (w > 0).astype(np.float64) @ ox.T
    if weighted:
        num = oy @ (f * w) @ ox.T
        den = oy @ w @ ox.T
        sb = np.zeros_like(num)
        good = den > 0
        sb[good] = num[good] / den[good] / pixel_arcsec**2
    else:
        sb = oy @ np.where(w > 0, f, 0.0) @ ox.T / pixel_arcsec**2
    return sb.astype(np.float32), np.clip(coverage, 0.0, 1.0).astype(np.float32)


def masked_smooth(image, mask, sigma_pix):
    """Gaussian smoothing over ``mask`` only (normalized convolution).

    Edges of the covered area are not darkened; pixels outside the mask are 0.
    """
    from scipy.ndimage import gaussian_filter

    image = np.asarray(image, dtype=np.float64)
    if sigma_pix <= 0:
        return np.where(mask, image, 0.0).astype(np.float32)
    weights = gaussian_filter(mask.astype(np.float64), sigma_pix, mode="constant")
    smoothed = gaussian_filter(np.where(mask, image, 0.0), sigma_pix, mode="constant")
    out = np.zeros_like(image)
    ok = mask & (weights > 1e-3)
    out[ok] = smoothed[ok] / weights[ok]
    return out.astype(np.float32)


def zero_padded_smooth(image, sigma_pix):
    """Gaussian smoothing with zero padding, as LEMUR's AstroCLIP baseline does."""
    from scipy.ndimage import gaussian_filter

    if sigma_pix <= 0:
        return np.asarray(image, dtype=np.float32)
    return gaussian_filter(
        np.asarray(image, dtype=np.float64), sigma_pix, mode="constant", truncate=3.0
    ).astype(np.float32)
