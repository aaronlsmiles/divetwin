import numpy as np
import pytest

import heat


def test_both_ramps_are_monotone_in_luminance_and_share_their_steps():
    t = np.linspace(0, 1, 101)
    for stops in (heat.POSITIVE, heat.NEGATIVE):
        lum = heat.luminance(heat.ramp(stops, t))
        assert np.all(np.diff(lum) > 0)
    lp = heat.luminance(np.array([c for _, c in heat.POSITIVE]))
    ln = heat.luminance(np.array([c for _, c in heat.NEGATIVE]))
    assert np.allclose(lp, ln, atol=25)                              # the same lightness steps, so sign changes hue only
    assert heat.POSITIVE[1][1][0] > heat.POSITIVE[1][1][2] and heat.NEGATIVE[1][1][2] > heat.NEGATIVE[1][1][0]   # warm vs cool


def _lin(c):
    c = np.asarray(c, float) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lstar(rgb):
    y = _lin(rgb) @ np.array([0.2126, 0.7152, 0.0722])
    return np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)


def test_blended_lightness_follows_magnitude_on_any_frame():
    """Constant alpha over a dimmed grey frame: |r| alone sets the lightness, whatever the frame is (call 69 review, I2)."""
    r = np.linspace(0.0, 0.5, 26)
    for level in (20, 60, 112, 160, 200, 250):
        f = np.full((1, len(r), 3), level, np.uint8)
        for sign in (1, -1):
            out = heat.heat_overlay(f, (sign * r)[None])
            L = _lstar(out[0, :, ::-1])
            assert np.all(np.diff(L) > 0), (level, sign, np.round(L, 1))


def test_the_frame_shows_through_only_as_a_dimmed_greyscale_under_a_constant_alpha():
    assert heat.ALPHA == pytest.approx(0.8) and 0.0 < heat.DIM < 1.0
    f = np.zeros((1, 2, 3), np.uint8)
    f[0, 0], f[0, 1] = (128, 128, 128), (0, 103, 255)        # BGR: a grey and an orange of the same luminance
    assert heat.luminance(f[0, 0, ::-1]) == pytest.approx(heat.luminance(f[0, 1, ::-1]), abs=0.5)
    out = heat.heat_overlay(f, np.array([[0.25, 0.25]])).astype(int)
    assert np.abs(out[0, 0] - out[0, 1]).max() <= 1               # the frame's hue does not leak into the heat


def test_zero_residual_is_a_dark_ramp_end_and_never_the_unverified_look():
    for level in (20, 60, 112, 128, 160, 250):
        f = np.full((8, 8, 3), level, np.uint8)
        r = np.zeros((8, 8))
        out = heat.heat_overlay(f, r).astype(float)
        r[:] = np.nan
        hatch = heat.heat_overlay(f, r).astype(float)
        assert not np.array_equal(out[0, 0], f[0, 0]) and heat.luminance(out[0, 0, ::-1]) < 60      # the dark ramp end
        for g in heat.HATCH_GREYS:
            assert np.abs(out[0, 0] - g).max() > 25                                                   # never either hatch grey
        assert set(np.unique(hatch)) == set(heat.HATCH_GREYS)


def test_unverified_pixels_are_a_45_degree_hatch_that_ignores_the_frame():
    rng = np.random.default_rng(0)
    f = rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)
    r = np.full((16, 16), np.nan)
    out = heat.heat_overlay(f, r)
    assert np.array_equal(out, heat.heat_overlay(255 - f, r))             # the frame's own texture never shows
    g = out[..., 0]
    assert (out[..., 0] == out[..., 1]).all() and (out[..., 0] == out[..., 2]).all() and set(np.unique(g)) == set(heat.HATCH_GREYS)
    assert (g[0, :5] == g[0, 0]).all() and g[0, 6] != g[0, 0]             # 4 px across the stripe = 5.66 px along an axis
    assert (g[1:, :-1] == g[:-1, 1:]).all()                               # constant along x + y: a 45 degree line
    assert np.array_equal(heat.hatch(16, 16), g)
    one = np.zeros((16, 16))
    one[3, 3] = np.nan
    assert heat.heat_overlay(f, one)[3, 3, 0] == heat.hatch(16, 16)[3, 3] and not np.array_equal(heat.heat_overlay(f, one)[4, 4], f[4, 4])


def test_magnitude_is_clipped_at_half_and_sign_picks_the_hue():
    f = np.full((1, 4, 3), 100, np.uint8)
    r = np.array([[0.25, 0.5, 5.0, -0.5]])
    out = heat.heat_overlay(f, r)
    assert np.array_equal(out[0, 1], out[0, 2])                       # 0.5 and 5.0 are the same (clip)
    rgb = out[0, :, ::-1].astype(int)
    assert rgb[1, 0] > rgb[1, 2] and rgb[3, 2] > rgb[3, 0]            # positive reads warm, negative cool
    assert heat.luminance(out[0, 1, ::-1]) > heat.luminance(out[0, 0, ::-1])      # more residual, lighter
    assert not np.array_equal(out[0, 0], f[0, 0])


def test_a_grey_frame_is_every_pixel_unverified():
    f = np.full((6, 6, 3), 30, np.uint8)
    g = heat.grey_frame(f)
    assert np.array_equal(g[..., 0], heat.hatch(6, 6)) and set(np.unique(g)) == set(heat.HATCH_GREYS)


def test_the_real_pane_has_one_grey_for_unseen_and_past_the_cap():
    assert heat.GREY_RGB == (112, 112, 112) == (sum(heat.HATCH_GREYS) // 2,) * 3


def test_palette_json_carries_the_ramps_for_the_page():
    p = heat.palette_json()
    assert p["clip"] == 0.5 and len(p["positive"]) == 3 and p["alpha"] == 0.8 and p["dim"] == heat.DIM
    assert "nearer" in p["positive_means"] and "farther" in p["negative_means"]


def test_the_legend_says_hatched_is_unverified_and_gives_two_reasons():
    """A tracked moving object is no longer a reason (call 69): it is drawn, outlined, and not counted in D."""
    p = heat.palette_json()
    assert p["unverified"] == "hatched = unverified"
    assert p["unverified_hatch"] == {"angle_deg": 45, "stripe_px": 4, "greys": [96, 128]}
    reasons = " | ".join(p["unverified_reasons"])
    assert len(p["unverified_reasons"]) == 2 and "no real camera saw it" in reasons and "past the trusted range" in reasons
    assert "moving" not in reasons
    assert p["unseen_rgb"] == [112, 112, 112] and "unverified_rgb" not in p


def test_the_legend_says_outlined_is_a_tracked_moving_object_drawn_but_not_counted_in_d():
    p = heat.palette_json()
    assert p["outlined"] == "outlined: a tracked moving object, drawn but not counted in D"
    assert p["outline"] == {"rgb": list(heat.OUTLINE_RGB), "width_px": 2}


def test_the_hatch_stripes_are_four_px_across_the_stripe_so_the_legend_is_true():
    """The stripes ran 4 px along each axis, which is 2.8 px across (call 69 review): now 4 px perpendicular to the line."""
    g = heat.hatch(8, 400)[0].astype(int)
    edges = np.flatnonzero(np.diff(g) != 0)
    along_x = np.diff(edges).mean()                       # the stripe's width measured along the x axis
    assert along_x / np.sqrt(2) == pytest.approx(heat.HATCH_STRIPE_PX, abs=0.1)
    assert heat.palette_json()["unverified_hatch"]["stripe_px"] == heat.HATCH_STRIPE_PX == 4


def _frame_and_r(value=0.25, n=24):
    f = np.random.default_rng(1).integers(0, 255, (n, n, 3), dtype=np.uint8)
    return f, np.full((n, n), value)


def test_a_tracked_object_is_drawn_with_its_residual_and_outlined_in_a_two_px_band():
    f, r = _frame_and_r()
    mask = np.zeros(r.shape, bool)
    mask[8:16, 8:16] = True
    base, out = heat.heat_overlay(f, r), heat.heat_overlay(f, r, track=mask)
    outline_bgr = np.array(heat.OUTLINE_RGB[::-1], np.uint8)
    diff = np.any(out != base, axis=-1)
    assert diff.any() and (out[diff] == outline_bgr).all()           # the only change is the outline's colour
    assert (out[10:14, 10:14] == base[10:14, 10:14]).all()          # inside: the same signed palette as a verified pixel
    assert (out[:6] == base[:6]).all()                              # far from the track: untouched
    for y in (7, 8, 15, 16):                                         # a 2 px band straddling the edge, all round
        assert (out[y, 12] == outline_bgr).all() and (out[12, y] == outline_bgr).all()
    for y in (6, 9, 14, 17):
        assert (out[y, 12] == base[y, 12]).all() and (out[12, y] == base[12, y]).all()


def test_an_object_at_the_edge_of_the_frame_is_not_outlined_along_the_frame_edge():
    f, r = _frame_and_r()
    mask = np.zeros(r.shape, bool)
    mask[:6, :6] = True
    base, out = heat.heat_overlay(f, r), heat.heat_overlay(f, r, track=mask)
    assert (out[0, 2] == base[0, 2]).all() and (out[2, 0] == base[2, 0]).all()
    assert (out[5, 2] == np.array(heat.OUTLINE_RGB[::-1])).all()


def test_pixels_the_render_never_saw_stay_hatched_inside_a_track():
    f, r = _frame_and_r()
    mask = np.zeros(r.shape, bool)
    mask[6:18, 6:18] = True
    r[10:13, 10:13] = np.nan
    out = heat.heat_overlay(f, r, track=mask)
    assert np.array_equal(out[10:13, 10:13, 0], heat.hatch(24, 24)[10:13, 10:13])
    assert not np.isin(out[14, 14], heat.HATCH_GREYS).all()          # the pixels beside it are drawn


def test_the_outline_colour_is_neither_a_ramp_stop_nor_a_hatch_grey():
    o = np.array(heat.OUTLINE_RGB, float)
    for stops in (heat.POSITIVE, heat.NEGATIVE):
        for _, c in stops:
            assert np.abs(o - np.array(c, float)).max() > 25
    for g in heat.HATCH_GREYS:
        assert np.abs(o - g).max() > 25


def test_a_grey_frame_has_no_outline_and_a_track_off_the_frame_grid_is_refused():
    f = np.full((6, 6, 3), 30, np.uint8)
    assert np.array_equal(heat.grey_frame(f)[..., 0], heat.hatch(6, 6))
    with pytest.raises(AssertionError):
        heat.heat_overlay(f, np.zeros((6, 6)), track=np.zeros((6, 7), bool))


def test_the_floor_preview_has_its_own_neutral_ramp_not_the_residuals():
    assert heat.FLOOR_RAMP != heat.POSITIVE and heat.FLOOR_RAMP != heat.NEGATIVE
    hues = np.array([c for _, c in heat.FLOOR_RAMP], float)
    assert (hues[:, 1] < hues[:, 0]).all() and (hues[:, 1] < hues[:, 2]).all()          # one hue family: violet (G lowest)
    assert np.all(np.diff(heat.luminance(heat.ramp(heat.FLOOR_RAMP, np.linspace(0, 1, 101)))) > 0)


def test_shape_mismatch_is_refused():
    with pytest.raises(AssertionError):
        heat.heat_overlay(np.zeros((4, 4, 3), np.uint8), np.zeros((4, 5)))


def test_palette_json_carries_the_floor_maps_ramp_and_says_what_the_map_is_without_calling_it_the_floor():
    """Call 85: the floor map sits beside the heat on the page, which draws its key from this JSON, so no violet is typed there."""
    p = heat.palette_json()
    assert p["floor_ramp"] == [[t, list(c)] for t, c in heat.FLOOR_RAMP]
    assert p["floor_means"] == heat.FLOOR_MEANS == "where mono depth already errs on the real tank; display only, the same for every frame"
    assert "floor" not in p["floor_means"]                  # the floor is the one number D is divided by; this is a picture of where the error lives
    assert p["floor_ramp"] != p["positive"] and p["floor_ramp"] != p["negative"]
