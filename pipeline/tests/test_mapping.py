import numpy as np
import pytest

from mapping import FILL_1280x720, box_affine, box_intrinsics, candidate_boxes, measure_box, resample, warp_image
from units import Intrinsics

K = Intrinsics(1433.347, 1433.347, 1156.798, 631.871, 2208, 1242)


def _texture(seed=0):
    rng = np.random.default_rng(seed)
    small = rng.uniform(0, 255, (78, 138, 3)).astype(np.float32)
    import cv2
    return np.clip(cv2.resize(small, (2208, 1242), interpolation=cv2.INTER_CUBIC), 0, 255).astype(np.uint8)


def test_box_intrinsics_agree_with_the_affine():
    X = np.array([120.0, -40.0, 900.0])
    u = K.fx * X[0] / X[2] + K.cx
    v = K.fy * X[1] / X[2] + K.cy
    for box, (w, h) in ((FILL_1280x720, (1280, 720)), (candidate_boxes(2208, 1242, 1280, 704)["cover"], (1280, 704))):
        ke = box_intrinsics(K, box, w, h)
        ue, ve = box_affine(box, w, h) @ np.array([u, v, 1.0])
        assert ke.fx * X[0] / X[2] + ke.cx == pytest.approx(ue)
        assert ke.fy * X[1] / X[2] + ke.cy == pytest.approx(ve)


def test_sixteen_by_nine_has_one_candidate():
    assert list(candidate_boxes(2208, 1242, 1280, 720)) == ["fill"]
    assert set(candidate_boxes(2208, 1242, 1280, 704)) == {"fill", "cover", "contain"}


def test_cover_crop_is_eight_rows_each_side():
    x0, y0, w, h = candidate_boxes(2208, 1242, 1280, 704)["cover"]
    assert x0 == pytest.approx(0) and w == pytest.approx(2208)
    assert y0 * 1280 / 2208 == pytest.approx(8.0)


@pytest.mark.parametrize("name", ["fill", "cover", "contain"])
def test_measure_box_finds_the_engine_framing(name):
    img = _texture()
    box = candidate_boxes(2208, 1242, 1280, 704)[name]
    engine0 = warp_image(img, box, 1280, 704)
    out = measure_box(img, engine0)
    assert out["name"] == name and out["ok"], out


def test_measure_box_rejects_a_shifted_frame():
    img = _texture(1)
    box = candidate_boxes(2208, 1242, 1280, 704)["cover"]
    shifted = (box[0] + 6 * 2208 / 1280, box[1], box[2], box[3])  # 6 engine pixels off
    out = measure_box(img, warp_image(img, shifted, 1280, 704))
    assert not out["ok"]


def test_resample_keeps_values_and_marks_holes():
    arr = np.full((1242, 2208), 50.0, np.float32)
    valid = np.ones_like(arr, bool)
    valid[:, :400] = False
    out, ok = resample(arr, valid, FILL_1280x720, 1280, 720)
    assert np.allclose(out[ok], 50.0, atol=1e-4)
    assert not ok[:, :200].any() and ok[:, 300:].all()


def test_fill_warp_matches_cv2_resize_when_enlarging():
    """Pins the half-pixel convention independently of box_affine's own algebra (no prefilter when enlarging)."""
    import cv2
    rng = np.random.default_rng(3)
    img = rng.uniform(0, 255, (78, 138, 3)).astype(np.float32)
    h, w = img.shape[:2]
    out = warp_image(img, (0.0, 0.0, float(w), float(h)), 1280, 720)
    ref = cv2.resize(img, (1280, 720), interpolation=cv2.INTER_LINEAR)
    assert np.abs(out - ref).max() < 0.01
