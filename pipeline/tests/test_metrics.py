import numpy as np
import pytest

from metrics import (abs_rel, at_seconds, divergence, first_sustained, first_wall_frame, lost_from, noise_floor,
                     verified_share)


def test_abs_rel_ignores_nan_and_mask():
    r = np.array([[0.1, -0.3], [np.nan, 5.0]])
    m = np.array([[True, True], [True, False]])
    assert abs_rel(r, m) == pytest.approx(0.2)


def test_floor_and_divergence():
    f = noise_floor([0.1, 0.2, np.nan, 0.3])
    assert f == pytest.approx(0.2)
    assert divergence(np.array([0.2, 0.6]), f).tolist() == pytest.approx([1.0, 3.0])


def test_verified_share():
    s = np.zeros((10, 10), bool)
    s[:4] = True
    assert verified_share(s) == pytest.approx(0.4)


def test_at_seconds_on_121_frames():
    D = np.arange(121, dtype=float)
    out = at_seconds(D)
    assert out == {"0": 0.0, "1": 24.0, "2.5": 60.0, "5": 120.0, "10": None}


def test_at_seconds_ten_second_clip():
    assert at_seconds(np.arange(241, dtype=float))["10"] == 240.0


def test_first_sustained_needs_twelve_in_a_row():
    D = np.ones(60)
    D[10:21] = 4.0  # eleven frames: not enough
    assert first_sustained(D) is None
    D[30:42] = 4.0  # twelve
    assert first_sustained(D) == 30
    D2 = np.ones(30)
    D2[5:20] = 4.0
    D2[10] = np.nan
    assert first_sustained(D2) is None


def test_wall_frame_and_lost():
    fwd = np.array([0, 100, 400, 900, 1400, 1500.0])
    assert first_wall_frame(fwd, 1300.0, np.zeros(6, bool)) == 4
    lost = np.array([False, False, False, True, True, True])
    assert first_wall_frame(fwd, 1300.0, lost) is None


def test_lost_from():
    fit = np.array([1.0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.7, 0.3, 0.9])
    assert lost_from(fit, np.full(9, 1000)) == 7
    assert lost_from(np.full(5, 0.8), np.array([1000, 1000, 50, 1000, 1000])) == 2
