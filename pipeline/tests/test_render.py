import numpy as np
import pytest

from camera import Pose, rot_y
from recon import build_mesh
from render import render
from synth import K_SMALL, corridor_colors, corridor_depth

CUBE = ((-60.0, 60.0), (60.0, 180.0), (500.0, 600.0))


@pytest.fixture(scope="module")
def tank():
    z = corridor_depth(K_SMALL, Pose.identity())
    return z, build_mesh(z, K_SMALL, corridor_colors(K_SMALL, Pose.identity(), z))


def test_render_from_identity_reproduces_depth_and_colour(tank):
    z, mesh = tank
    r = render(mesh, K_SMALL, Pose.identity())
    inner = np.zeros_like(r.seen)
    inner[1:-1, 1:-1] = True
    assert r.seen[inner].mean() > 0.99
    ok = r.seen & inner
    assert np.nanmax(np.abs(r.depth[ok] - z[ok]) / z[ok]) < 1e-3


def test_render_forward_matches_truth(tank):
    _, mesh = tank
    pose = Pose(np.eye(3), np.array([0.0, 0.0, 200.0]))
    r = render(mesh, K_SMALL, pose)
    truth = corridor_depth(K_SMALL, pose)
    assert r.seen.mean() > 0.97  # moving straight ahead keeps the view inside what was seen
    rel = np.abs(r.depth[r.seen] - truth[r.seen]) / truth[r.seen]
    assert np.percentile(rel, 99) < 0.01


def test_yaw_exposes_unseen_edge(tank):
    _, mesh = tank
    r = render(mesh, K_SMALL, Pose(rot_y(np.deg2rad(25)), np.zeros(3)))
    assert r.seen.mean() < 0.97
    assert r.seen[:, :40].mean() > r.seen[:, -40:].mean()  # turning right: the right edge was never seen
    assert np.all(r.color[~r.seen] == 128)


def test_cube_leaves_a_hole_not_a_stretch():
    z = corridor_depth(K_SMALL, Pose.identity(), CUBE)
    mesh = build_mesh(z, K_SMALL)
    pose = Pose(np.eye(3), np.array([150.0, 0.0, 0.0]))  # step sideways: the wall behind the cube appears
    r = render(mesh, K_SMALL, pose)
    truth = corridor_depth(K_SMALL, pose, CUBE)
    rel = np.abs(r.depth[r.seen] - truth[r.seen]) / truth[r.seen]
    assert np.percentile(rel, 99.5) < 0.01   # nothing seen is wrong ...
    assert (~r.seen).sum() > 100              # ... and the disocclusion is grey
