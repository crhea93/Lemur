"""Intensity transforms into [0, 1] for the model.

Both modes use LEMUR's AstroCLIP stretch,

    v = asinh(clip((x - vmin) / (vmax - vmin), 0, 1) / a) / asinh(1 / a),

and differ only in where vmin and vmax come from:

- ``morphology``: per image, percentiles of its covered positive pixels
  (LEMUR's baseline uses all positive pixels). Removes depth and luminosity,
  so only the shape of the emission is compared.
- ``physical``: one vmin and vmax for every image, either given in the config
  or fitted once from the pooled LEMUR and mock pixels (``fit_physical``).
  Keeps absolute surface brightness, optionally corrected for cosmological
  dimming by (1 + z)^dimming_exponent; compare at matched redshift otherwise.

Pixels outside the mask are set to 0 and reported separately.
"""

import numpy as np


def asinh_stretch(image, vmin, vmax, a):
    if not vmax > vmin:
        return np.zeros_like(image, dtype=np.float32)
    scaled = np.clip((np.asarray(image, dtype=np.float64) - vmin) / (vmax - vmin), 0, 1)
    return (np.arcsinh(scaled / a) / np.arcsinh(1.0 / a)).astype(np.float32)


def percentile_limits(image, mask, lower_pct, upper_pct):
    """(vmin, vmax) from the positive pixels in ``mask``, or (0, 0) if none."""
    values = np.asarray(image)[mask]
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return 0.0, 0.0
    vmin, vmax = np.percentile(values, [lower_pct, upper_pct])
    if vmax <= vmin:
        vmin, vmax = values.min(), values.max()
    return float(vmin), float(vmax)


def morphology(image, mask, lower_pct=5.0, upper_pct=99.7, asinh_a=0.08):
    """Per-image stretch. Returns (values, vmin, vmax)."""
    vmin, vmax = percentile_limits(image, mask, lower_pct, upper_pct)
    out = asinh_stretch(image, vmin, vmax, asinh_a)
    out[~mask] = 0.0
    return out, vmin, vmax


def dimming_factor(redshift, exponent):
    if not exponent or redshift is None:
        return 1.0
    return float((1.0 + redshift) ** exponent)


def physical(image, mask, redshift, vmin, vmax, asinh_a=0.08, dimming_exponent=0):
    """Shared stretch of surface brightness, after optional dimming correction."""
    out = asinh_stretch(
        np.asarray(image) * dimming_factor(redshift, dimming_exponent), vmin, vmax, asinh_a
    )
    out[~mask] = 0.0
    return out


def fit_physical(images, masks, redshifts, lower_pct, upper_pct, dimming_exponent=0, groups=None, max_pixels=2_000_000, seed=0):
    """Global (vmin, vmax) from the pooled positive covered pixels.

    ``groups`` (e.g. the source of each image) gives every group equal weight
    in the pool, so the larger sample does not set the scale alone.
    """
    rng = np.random.default_rng(seed)
    groups = np.asarray(groups if groups is not None else ["all"] * len(images))
    names = sorted(set(groups))
    per_group = max_pixels // len(names)
    pool, weights = [], []
    for name in names:
        values = [
            np.asarray(img)[m] * dimming_factor(z, dimming_exponent)
            for img, m, z, g in zip(images, masks, redshifts, groups)
            if g == name
        ]
        values = np.concatenate(values) if values else np.zeros(0)
        values = values[np.isfinite(values) & (values > 0)]
        if values.size > per_group:
            values = rng.choice(values, per_group, replace=False)
        if values.size:
            pool.append(values)
            weights.append(np.full(values.size, 1.0 / values.size))
    if not pool:
        raise ValueError("no positive covered pixels to fit the physical scale")
    pool, weights = np.concatenate(pool), np.concatenate(weights)
    order = np.argsort(pool)
    pool, cumulative = pool[order], np.cumsum(weights[order])
    cumulative /= cumulative[-1]
    vmin, vmax = (
        float(pool[min(np.searchsorted(cumulative, pct / 100.0), pool.size - 1)])
        for pct in (lower_pct, upper_pct)
    )
    return vmin, vmax
