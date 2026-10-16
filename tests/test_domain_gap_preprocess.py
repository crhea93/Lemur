"""Tests of the domain-gap preprocessing (spatial resampling, masks, intensity)."""

import numpy as np
import pytest

from domain_gap import intensity, spatial


def test_overlap_rows_sum_to_one_inside_the_image():
    m = spatial.overlap_matrix(start=10.3, side=50.0, n_out=7, first_pixel=0, n_in=100)
    assert np.allclose(m.sum(axis=1), 1.0)


def test_overlap_counts_pixels_off_the_image_as_uncovered():
    # The field spans [-5.5, 4.5): half of it is off the image.
    m = spatial.overlap_matrix(start=-5.5, side=10.0, n_out=2, first_pixel=0, n_in=20)
    assert np.allclose(m.sum(axis=1), [0.0, 1.0])


def test_extract_of_constant_image_is_constant_surface_brightness():
    flux = np.full((200, 200), 3.0)
    weight = np.ones_like(flux)
    sb, cov = spatial.extract(flux, weight, (99.5, 99.5), 64.0, 16, pixel_arcsec=0.5)
    assert np.allclose(sb, 3.0 / 0.25)
    assert np.allclose(cov, 1.0)


def test_extract_weighted_mean_is_counts_over_exposure():
    rng = np.random.default_rng(1)
    counts = rng.poisson(2.0, (40, 40)).astype(float)
    exposure = rng.uniform(0.5, 2.0, (40, 40))
    flux = counts / exposure
    sb, _ = spatial.extract(flux, exposure, (19.5, 19.5), 40.0, 1, pixel_arcsec=1.0)
    assert sb[0, 0] == pytest.approx(counts.sum() / exposure.sum())


def test_extract_coverage_at_the_image_edge():
    flux = np.ones((100, 100))
    weight = np.ones_like(flux)
    # Centre on the left edge (pixel -0.5): the left half of the field is off the image.
    sb, cov = spatial.extract(flux, weight, (-0.5, 49.5), 40.0, 4, pixel_arcsec=1.0)
    assert np.allclose(cov[:, :2], 0.0) and np.allclose(cov[:, 2:], 1.0)
    assert np.allclose(sb[:, 2:], 1.0) and np.allclose(sb[:, :2], 0.0)


def test_extract_ignores_unexposed_pixels_when_weighted():
    flux = np.ones((100, 100))
    weight = np.ones_like(flux)
    weight[:, :50] = 0.0  # a chip gap: F is meaningless there
    flux[:, :50] = 99.0
    sb, cov = spatial.extract(flux, weight, (49.5, 49.5), 100.0, 2, pixel_arcsec=1.0)
    assert np.allclose(sb[:, 1], 1.0) and np.allclose(sb[:, 0], 0.0)
    assert np.allclose(cov[:, 0], 0.0)


def test_unweighted_extract_counts_uncovered_area_as_zero():
    flux = np.ones((100, 100))
    weight = np.ones_like(flux)
    weight[:, :25] = 0.0
    sb, _ = spatial.extract(flux, weight, (49.5, 49.5), 100.0, 1, 1.0, weighted=False)
    assert sb[0, 0] == pytest.approx(0.75)


def test_physical_field_shrinks_with_redshift():
    near = spatial.field_side_arcsec({"kpc": 500}, 0.05)
    far = spatial.field_side_arcsec({"kpc": 500}, 0.2)
    assert near > far > 0
    assert spatial.field_side_arcsec({"kpc": 500}, None) is None
    assert spatial.field_side_arcsec({"native_pixels": 512}) == pytest.approx(251.904)


def test_masked_smooth_does_not_darken_edges():
    image = np.ones((20, 20))
    mask = np.zeros((20, 20), bool)
    mask[:, :10] = True
    out = spatial.masked_smooth(image, mask, 2.0)
    assert np.allclose(out[:, :10], 1.0) and np.allclose(out[:, 10:], 0.0)


def test_zero_padded_smooth_matches_lemur_baseline():
    from domain_gap.io import astroclip_script

    rng = np.random.default_rng(2)
    image = rng.normal(size=(64, 64))
    ref = astroclip_script().gaussian_smooth(image, 1.5)
    assert np.allclose(spatial.zero_padded_smooth(image, 1.5), ref, atol=1e-5)


def test_morphology_matches_lemur_stretch_without_mask():
    from domain_gap.io import astroclip_script

    rng = np.random.default_rng(3)
    image = rng.normal(0.1, 1.0, (64, 64))
    ours, _, _ = intensity.morphology(image, np.ones_like(image, bool))
    assert np.allclose(ours, astroclip_script().stretch_image(image), atol=1e-6)


def test_morphology_uses_only_covered_pixels_and_zeroes_the_rest():
    image = np.ones((10, 10))
    image[0, 0] = 1e6  # bright but uncovered
    mask = np.ones_like(image, bool)
    mask[0, 0] = False
    out, vmin, vmax = intensity.morphology(image, mask)
    assert vmax == 1.0 and out[0, 0] == 0.0


def test_physical_stretch_is_shared_not_per_image():
    mask = np.ones((4, 4), bool)
    faint = intensity.physical(np.full((4, 4), 1.0), mask, 0.1, 0.0, 10.0)
    bright = intensity.physical(np.full((4, 4), 5.0), mask, 0.1, 0.0, 10.0)
    assert bright.mean() > faint.mean()
    assert 0.0 <= faint.min() and bright.max() <= 1.0


def test_fit_physical_weights_groups_equally():
    big = [np.full((10, 10), 1.0)] * 50
    small = [np.full((10, 10), 100.0)]
    images = big + small
    masks = [np.ones((10, 10), bool)] * len(images)
    groups = ["a"] * 50 + ["b"]
    _, vmax = intensity.fit_physical(images, masks, [0.1] * 51, 0, 60, groups=groups)
    assert vmax == pytest.approx(100.0)  # half of the pool is group b
