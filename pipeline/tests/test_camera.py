import numpy as np
import pytest

from camera import Pose, rot_y, so3_exp, straight_path


def test_so3_exp_matches_rot_y():
    assert np.allclose(so3_exp(np.array([0.0, 0.3, 0.0])), rot_y(0.3))
    assert np.allclose(so3_exp(np.zeros(3)), np.eye(3))


def test_positive_yaw_turns_right():
    p = Pose(rot_y(np.deg2rad(10)), np.zeros(3))
    assert p.yaw_deg() == pytest.approx(10.0)
    assert p.R[:, 2][0] > 0  # the forward axis leans toward +x (right)


def test_to_world_applies_scale_rotation_and_centre():
    p = Pose(rot_y(np.pi / 2), np.array([1.0, 2.0, 3.0]), 2.0)
    assert np.allclose(p.to_world(np.array([[0.0, 0.0, 1.0]])), [[3.0, 2.0, 3.0]])


def test_straight_path_is_the_self_test_path():
    path = straight_path()
    assert len(path) == 49
    assert np.allclose(path[0].C, 0) and np.allclose(path[-1].C, [0, 0, 200])
    assert max(abs(p.yaw_deg()) for p in path) == pytest.approx(3.0, abs=1e-6)
