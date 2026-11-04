import warnings

import numpy as np
import pytest

from camera import Pose
from recon import build_mesh, far_end_depth, grid_normals, points_from_depth
from synth import K_SMALL, TANK, corridor_colors, corridor_depth


@pytest.fixture(scope="module")
def tank():
    z = corridor_depth(K_SMALL, Pose.identity())
    return z, build_mesh(z, K_SMALL, corridor_colors(K_SMALL, Pose.identity(), z))


def test_points_match_q_reprojection_up_to_sign():
    """The calibration's Q (OpenCV, right camera at +x) reprojects to minus these points."""
    fx, cx, cy, B = 1433.347, 1156.798, 631.871, 62.975
    Q = np.array([[1, 0, 0, -cx], [0, 1, 0, -cy], [0, 0, 0, fx], [0, 0, -1 / B, 0]])
    d = np.array([[40.0, 55.0], [90.0, 120.0]])
    from units import Intrinsics
    k = Intrinsics(fx, fx, cx, cy, 2, 2)
    P = points_from_depth(fx * B / d, k)
    for (v, u), dd in np.ndenumerate(d):
        X = Q @ np.array([u, v, dd, 1.0])
        assert np.allclose(X[:3] / X[3], -P[v, u], rtol=1e-12)


def test_normals_face_the_camera(tank):
    z, _ = tank
    n = grid_normals(points_from_depth(z, K_SMALL))
    far = n[85:95, 150:170]  # the far wall
    assert np.allclose(far[..., 2], -1.0, atol=1e-6)


def test_far_end_depth(tank):
    z, _ = tank
    assert far_end_depth(z) == pytest.approx(TANK["z_far"], rel=1e-6)


def test_far_end_needs_a_tenth_of_the_window():
    z = np.full((100, 100), 500.0)
    z[40:60, 40:60] = np.nan  # the whole central 20 x 20 window invalid
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert np.isnan(far_end_depth(z))
        z[40:41, 40:52] = 700.0  # 12 of 400 window pixels: 3 %
        assert np.isnan(far_end_depth(z))
        z[40:44, 40:52] = 700.0  # 48 of 400: 12 %
        assert far_end_depth(z) == pytest.approx(700.0)


def test_build_mesh_rejects_colours_on_another_grid():
    z = np.full((10, 12), 500.0)
    with pytest.raises(AssertionError):
        build_mesh(z, K_SMALL, np.zeros((12, 10, 3), np.uint8))


def test_normals_undefined_where_the_stencil_crosses_a_cut():
    z = np.full((20, 30), 500.0)
    z[:, 15:] = 1000.0  # a step: the cut lies between columns 14 and 15
    n = grid_normals(points_from_depth(z, K_SMALL))
    assert np.all(np.isnan(n[1:-1, 14:16]))
    assert np.all(np.isfinite(n[1:-1, 1:14])) and np.all(np.isfinite(n[1:-1, 16:-1]))
    assert np.allclose(n[1:-1, 2:13, 2], -1.0, atol=1e-6)
    z[:, 15:] = 520.0  # 4 %: below the 5 % jump, no cut
    assert np.all(np.isfinite(grid_normals(points_from_depth(z, K_SMALL))[1:-1, 1:-1]))
