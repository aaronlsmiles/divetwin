import numpy as np
import pytest

from units import bottle_depth, depth_to_disp, disp_to_depth, half_to_full, ratio_summary


def test_depth_and_disparity_are_inverse():
    d = np.array([10.0, 50.0, 0.0, np.nan, -3.0])
    z = disp_to_depth(d, 1433.347, 62.975)
    assert z[0] == pytest.approx(1433.347 * 62.975 / 10.0)
    assert np.isnan(z[2:]).all()
    assert depth_to_disp(z[:2], 1433.347, 62.975) == pytest.approx(d[:2])


def test_half_to_full_doubles_values_and_size():
    half = np.full((621, 1104), 40.0, np.float32)
    full = half_to_full(half, 2.0)
    assert full.shape == (1242, 2208)
    assert np.allclose(full, 80.0)


def test_bottle_depth_uses_eroded_median():
    d = np.full((200, 200), 100.0)
    m = np.zeros((200, 200), bool)
    m[50:150, 50:150] = True
    d[50:52, 50:150] = 10.0  # an edge row that erosion removes
    assert bottle_depth(d, m, 1000.0, 50.0) == pytest.approx(500.0)
    assert np.isnan(bottle_depth(d, np.zeros_like(m), 1000.0, 50.0))


def test_ratio_summary():
    s = ratio_summary({1: 200.0, 2: 400.0, 3: np.nan}, {1: 100.0, 2: 200.0, 3: 50.0})
    assert s["n"] == 2 and s["median"] == pytest.approx(2.0)


def test_epipolar_dy_on_a_textureless_pair_reports_no_matches():
    from units import epipolar_dy
    flat = np.full((200, 300), 128, np.uint8)
    assert epipolar_dy(flat, flat)["n"] == 0
