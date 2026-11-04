import numpy as np
import pytest

from realside import (classify_frames, classify_with_ious, exclusion_mask, progress, region_mad, start_and_tail, tank_median,
                      tail_min_obs, up_extend, xcheck)


def _plane(h=62, w=110):
    v = np.linspace(0, 1, h)[:, None]
    u = np.linspace(0, 1, w)[None, :]
    return (10.0 + 20.0 * v + 4.0 * u).astype(np.float32)


def _recording(n=30, h=62, w=110):
    """A tilted plane with a nearer blob that moves left to right; returns disps and blob masks."""
    plane = _plane(h, w)
    disps = np.repeat(plane[None], n, axis=0).copy()
    masks = np.zeros((n, h, w), bool)
    for k in range(n):
        x0 = int(k * (w - 12) / (n - 1))
        masks[k, 20:40, x0:x0 + 12] = True
        disps[k][masks[k]] = 60.0
    return plane, disps, masks


def test_up_extend_reaches_up_only():
    m = np.zeros((10, 3), bool)
    m[6, 1] = True
    e = up_extend(m, 3)
    assert e[:, 1].tolist() == [False, False, False, True, True, True, True, False, False, False]
    assert not e[:, 0].any() and not e[:, 2].any()


def test_up_extend_longer_than_frame():
    m = np.zeros((5, 2), bool)
    m[4, 0] = True
    assert up_extend(m, 50)[:, 0].all()


def test_exclusion_mask_grows_upward_more_than_down():
    b = np.zeros((200, 100), bool)
    b[120:140, 40:60] = True
    e = exclusion_mask(b, np.zeros_like(b), grid_scale=0.5)
    rows = np.where(e[:, 50])[0]
    assert rows.min() <= 120 - 30 - 7 + 1 and rows.max() <= 140 + 8


def test_masked_median_recovers_plane():
    plane, disps, masks = _recording()
    out = tank_median(disps, masks)
    ok = out["valid"]
    assert ok.mean() > 0.95
    assert np.allclose(out["tank_disp_half"][ok], plane[ok], atol=1e-5)


def test_unmasked_median_is_biased_where_blob_lingers():
    plane, disps, masks = _recording()
    disps[:, 20:40, -12:] = 60.0  # the blob rests at the right edge in every frame
    out = tank_median(disps, None)
    assert np.all(out["tank_disp_half"][20:40, -12:] == 60.0)


def test_tail_recipe_needs_ten_observations():
    plane = _plane()
    out = tank_median(np.repeat(plane[None], 9, axis=0), None)
    assert not out["valid"].any()
    out = tank_median(np.repeat(plane[None], 10, axis=0), None)
    assert out["valid"].all()


def test_classify_and_start():
    n, h, w = 8, 40, 40
    bottle = np.zeros((n, h, w), bool)
    hand = np.zeros((n, h, w), bool)
    for k in range(4):
        hand[k, 0:10, 5 + k:15 + k] = True
        bottle[k, 10:30, 5 + 2 * k:12 + 2 * k] = True
    bottle[4:6, 10:30, 20:27] = True  # bottle left standing for two frames
    states = classify_frames(bottle, hand)  # frames 6, 7: empty
    assert states == ["hand"] * 4 + ["quiet", "quiet", "empty", "empty"]
    info = start_and_tail(states)
    assert info["start"] == 7 and info["kind"] == "empty"
    assert info["tail"] == [6, 7] and info["tail_len"] == 2 and info["empty_tail_len"] == 2
    assert info["recipe"] == "tail"  # call 45: an empty tail builds the map at any length


def test_no_hand_free_frame_gives_no_start():
    info = start_and_tail(["hand"] * 5)
    assert info["start"] is None and info["tail"] is None and info["recipe"] == "masked"


def test_quiet_only_start():
    info = start_and_tail(["hand"] * 3 + ["quiet"] * 12)
    assert info["start"] == 14 and info["kind"] == "quiet" and info["recipe"] == "tail"


def test_region_mad_flags_the_odd_frame():
    rng = np.random.default_rng(0)
    base = rng.uniform(50, 200, (20, 30)).astype(np.float32)
    gray = np.repeat(base[None], 9, axis=0) * np.linspace(0.9, 1.1, 9)[:, None, None]
    gray[4, 5:15, 5:15] = 255.0
    mad = region_mad(gray, np.ones((20, 30), bool))
    assert mad.argmax() == 4 and mad[4] > 10 * np.median(mad)


def test_progress():
    assert progress([10, 15, 20]) == pytest.approx([0.0, 0.5, 1.0])


def test_start_comes_only_from_the_trailing_hand_free_run():
    info = start_and_tail(["empty"] * 5 + ["hand"] * 20 + ["quiet"] * 30)
    assert info["start"] == 54 and info["kind"] == "quiet"
    assert info["tail"] == [25, 54] and info["recipe"] == "tail"


def test_empty_before_the_hand_is_not_a_start_when_the_scene_ends_in_a_hand():
    # no hand-free tail at all: the old Gate S pick (last empty anywhere) is kept, with no tail
    info = start_and_tail(["empty"] * 5 + ["hand"] * 20)
    assert info["start"] == 4 and info["kind"] == "empty" and info["tail"] is None and info["recipe"] == "masked"


def test_start_prefers_the_last_empty_in_the_tail_over_a_later_quiet():
    info = start_and_tail(["hand"] * 2 + ["empty"] * 3 + ["quiet"] * 4)
    assert info["start"] == 4 and info["kind"] == "empty" and info["tail"] == [2, 4]


def test_tail_is_one_kind_only():
    info = start_and_tail(["hand"] * 3 + ["quiet"] * 6 + ["empty"] * 5)
    assert info["start"] == 13 and info["kind"] == "empty"
    assert info["tail"] == [9, 13] and info["tail_len"] == 5 and info["recipe"] == "tail"  # empty kind, call 45


@pytest.mark.parametrize("n_frames, recipe", [(9, "masked"), (10, "tail")])
def test_a_quiet_tail_needs_ten_frames(n_frames, recipe):
    info = start_and_tail(["hand"] * 2 + ["quiet"] * n_frames)
    assert info["kind"] == "quiet" and info["tail_len"] == n_frames and info["recipe"] == recipe


@pytest.mark.parametrize("n_empty", [1, 7, 9, 10])
def test_an_empty_tail_of_any_length_is_the_tail_recipe(n_empty):
    info = start_and_tail(["hand"] * 2 + ["empty"] * n_empty)
    assert info["kind"] == "empty" and info["tail_len"] == n_empty and info["recipe"] == "tail"


def test_a_quiet_tail_of_seven_stays_masked():
    info = start_and_tail(["hand"] * 2 + ["quiet"] * 7)
    assert info["kind"] == "quiet" and info["tail_len"] == 7 and info["recipe"] == "masked"


def test_mixed_kinds_do_not_count_toward_the_quiet_minimum():
    # 5 quiet + 5 empty: the tail is the 5 empty frames, which now builds the map by itself (call 45)
    info = start_and_tail(["hand"] + ["quiet"] * 5 + ["empty"] * 5)
    assert info["kind"] == "empty" and info["tail_len"] == 5 and info["recipe"] == "tail"


def test_no_tail_is_still_masked_even_if_the_start_is_empty():
    info = start_and_tail(["empty"] * 5 + ["hand"] * 20)
    assert info["kind"] == "empty" and info["tail_len"] == 0 and info["recipe"] == "masked"


def test_short_tail_median_needs_all_its_frames_up_to_ten():
    assert tail_min_obs(1) == 1 and tail_min_obs(7) == 7 and tail_min_obs(10) == 10 and tail_min_obs(61) == 10
    plane = _plane()
    for n in (1, 7):
        out = tank_median(np.repeat(plane[None], n, axis=0), None, min_obs=tail_min_obs(n))
        assert out["valid"].all() and np.allclose(out["tank_disp_half"], plane)


def test_rel_iqr_is_undefined_for_a_single_frame():
    out = tank_median(_plane()[None], None, min_obs=1)
    assert out["valid"].all() and np.isnan(out["rel_iqr"]).all()
    out = tank_median(np.repeat(_plane()[None], 2, axis=0), None, min_obs=1)
    assert np.isfinite(out["rel_iqr"]).all()


def test_xcheck_is_the_relative_difference_outside_masks_where_both_are_valid():
    a = np.full((10, 10), 100.0, np.float32)
    b = a * 1.10
    b[0, 0] = np.nan                   # invalid in one map
    b[1, 1] = 300.0                    # a big difference, but inside a mask
    excl = np.zeros((10, 10), bool)
    excl[1, 1] = True
    r = xcheck(a, b, excl)  # (tail map, masked map, every-mask union): |masked - tail| / tail
    assert r["n"] == 98 and r["med"] == pytest.approx(0.10, rel=1e-3) and r["p90"] == pytest.approx(0.10, rel=1e-3)
    assert xcheck(a, np.full_like(a, np.nan), excl)["n"] == 0


def _sliding(n=6, h=40, w=80, step=8):
    bottle = np.zeros((n, h, w), bool)
    for k in range(n):
        bottle[k, 10:30, step * k:step * k + 12] = True
    return bottle, np.zeros_like(bottle)


def test_a_sliding_bottle_is_moving():
    bottle, hand = _sliding()
    assert classify_frames(bottle, hand) == ["moving"] * 6


def test_classify_with_ious_gives_the_best_neighbour_iou():
    bottle, hand = _sliding()
    states, ious = classify_with_ious(bottle, hand)
    assert states == classify_frames(bottle, hand)
    assert len(ious) == 6
    assert ious == pytest.approx([4 / 20] * 6)  # 12 px wide, 8 px step: 4 shared of 20 in the union


def test_ious_are_none_without_a_bottle_to_compare():
    n, h, w = 5, 40, 40
    bottle = np.zeros((n, h, w), bool)
    hand = np.zeros((n, h, w), bool)
    hand[0, 0:10, 0:10] = True
    bottle[2:4, 10:30, 5:12] = True
    states, ious = classify_with_ious(bottle, hand)
    assert states == ["hand", "empty", "quiet", "quiet", "empty"]
    assert ious[0] is None and ious[1] is None and ious[4] is None
    assert ious[2] == pytest.approx(1.0) and ious[3] == pytest.approx(1.0)
