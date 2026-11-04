import numpy as np
import pytest

from align import huber_affine_fit, rel_residual


def _tank(h=180, w=320):
    v = np.linspace(0, 1, h)[:, None]
    u = np.linspace(0, 1, w)[None, :]
    return 20.0 + 30.0 * v + 5.0 * u  # disparity of a tilted surface, 20-55 px


def test_recovers_known_scale_and_shift():
    d = _tank()
    s, t = 2.5, -3.0
    g = (d - t) / s
    fit = huber_affine_fit(g, d, np.ones_like(d, bool))
    assert fit.s == pytest.approx(s, rel=1e-3)
    assert fit.t == pytest.approx(t, abs=1e-3 * np.median(d))


def test_planted_near_object_moves_fit_under_one_percent():
    d = _tank()
    s, t = 2.5, -3.0
    g = (d - t) / s
    mask = np.ones_like(d, bool)
    clean = huber_affine_fit(g, d, mask)
    g2 = g.copy()
    h, w = d.shape
    blob = np.zeros_like(mask)
    blob[int(0.35 * h):int(0.35 * h) + int(0.1 * h * 3.0), int(0.4 * w):int(0.4 * w) + int(w / 3.0)] = True
    assert 0.09 < blob.mean() < 0.11
    g2[blob] *= 1.8  # a near object the tank does not have
    planted = huber_affine_fit(g2, d, mask)
    change = np.abs(planted.apply(g) - clean.apply(g)) / d
    assert change.max() < 0.01


def test_planted_object_under_noise_still_under_one_percent():
    d = _tank()
    g = (d + 3.0) / 2.5
    rng = np.random.default_rng(1)
    noisy = d * (1 + 0.08 * rng.standard_normal(d.shape))
    g2 = g.copy()
    h, w = d.shape
    g2[int(0.35 * h):int(0.65 * h), int(0.4 * w):int(0.73 * w)] *= 1.8
    fit = huber_affine_fit(g2, noisy, np.ones_like(d, bool))
    assert np.max(np.abs(fit.apply(g) - d) / d) < 0.01


def test_identical_inputs_give_zero_residual():
    d = _tank()
    fit = huber_affine_fit(d, d, np.ones_like(d, bool))
    r = rel_residual(fit.apply(d), d)
    assert np.nanmax(np.abs(r)) < 1e-12


def test_residual_sign_positive_means_nearer():
    ref = np.full((4, 4), 10.0)
    assert np.all(rel_residual(ref * 1.2, ref) > 0)
    assert np.all(rel_residual(ref * 0.8, ref) < 0)


def test_too_few_pixels_raises():
    d = _tank()
    with pytest.raises(ValueError):
        huber_affine_fit(d, d, np.zeros_like(d, bool))


def test_degenerate_g_is_refused():
    d = _tank()
    with pytest.raises(ValueError, match="degenerate"):
        huber_affine_fit(np.full(d.shape, 0.5), d, np.ones_like(d, bool))
    with pytest.raises(ValueError, match="degenerate"):
        huber_affine_fit(0.5 + 1e-12 * np.random.default_rng(0).standard_normal(d.shape), d, np.ones_like(d, bool))
