import numpy as np
import pytest

pytest.importorskip("scipy")

from Pipeline import center  # noqa: E402

PIXEL = 3.936  # arcsec, 8x-binned ACIS


def _beta(shape, x0, y0, norm, core_pix):
    yy, xx = np.indices(shape)
    r2 = (xx - x0) ** 2 + (yy - y0) ** 2
    return norm * (1.0 + r2 / core_pix**2) ** -1.5


def _field(shape=(300, 300), seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(1.0, 0.05, size=shape), np.ones(shape)


def test_find_xray_peak_prefers_extended_cluster_over_point_source():
    data, exposure = _field()
    data += _beta(data.shape, 180, 120, norm=3.0, core_pix=8)
    data[250, 60] += 500.0  # bright point source
    x, y = center.find_xray_peak(data, exposure, PIXEL)
    assert abs(x - 180) <= 2 and abs(y - 120) <= 2


def test_find_xray_peak_ignores_unexposed_regions():
    data, exposure = _field()
    data += _beta(data.shape, 150, 150, norm=2.0, core_pix=8)
    exposure[:, :40] = 0.0
    data[:, :40] = 50.0  # garbage where there is no exposure
    x, y = center.find_xray_peak(data, exposure, PIXEL)
    assert abs(x - 150) <= 2 and abs(y - 150) <= 2


def test_find_xray_peak_prior_keeps_nearby_cluster_unless_far_one_dominates():
    data, exposure = _field()
    data += _beta(data.shape, 80, 80, norm=1.0, core_pix=8)
    data += _beta(data.shape, 220, 220, norm=1.5, core_pix=8)
    x, y = center.find_xray_peak(data, exposure, PIXEL, prior_xy=(85, 75))
    assert abs(x - 80) <= 2 and abs(y - 80) <= 2

    data, exposure = _field()
    data += _beta(data.shape, 80, 80, norm=0.3, core_pix=8)
    data += _beta(data.shape, 220, 220, norm=3.0, core_pix=8)
    x, y = center.find_xray_peak(data, exposure, PIXEL, prior_xy=(85, 75))
    assert abs(x - 220) <= 2 and abs(y - 220) <= 2


def test_find_xray_peak_maps_back_to_native_pixels():
    data, exposure = _field(shape=(160, 160))
    data += _beta(data.shape, 100, 60, norm=3.0, core_pix=6)
    native = np.kron(data, np.ones((8, 8)))
    x, y = center.find_xray_peak(native, np.kron(exposure, np.ones((8, 8))), 0.492)
    assert abs(x - (100 * 8 + 3.5)) <= 16 and abs(y - (60 * 8 + 3.5)) <= 16


def test_compute_center_falls_back_to_initial_coordinates(tmp_path):
    stored = {}

    class Service:
        def upsert_center(self, name, **kwargs):
            stored.update(kwargs)

        def get_center(self, name):
            return stored

    result = center.compute_center(
        "X", tmp_path / "missing.img", "01:02:03", "-01:02:03", Service()
    )
    assert result["method"] == "placeholder_existing_centroid"
    assert result["center_ra"] == "01:02:03"
