"""Settled offline on 3 Nov (sub-plan A, question 1): the exported frames are cv2.remap'd with P1/P2
from cv2.stereoRectify(alpha=0, CALIB_ZERO_DISPARITY) on the raw factory calibration, so their focal
length is P1's 1433.347 px, not the SDK's rectified 1430.272 px."""
import json

import cv2
import numpy as np
import pytest

from recordings import data_root, recordings
from units import epipolar_dy

pytestmark = pytest.mark.skipif(not data_root().exists(), reason="DIVETWIN_DATA absent (public clone)")
RECS = recordings()


@pytest.mark.parametrize("cond", list(RECS))
def test_rectification_reproduces_p1_p2(cond):
    cal = json.loads(RECS[cond].calibration_path.read_text())
    raw = cal["sources"]["raw"]
    K = {s: np.array([[raw[s]["fx"], 0, raw[s]["cx"]], [0, raw[s]["fy"], raw[s]["cy"]], [0, 0, 1]]) for s in ("left", "right")}
    dist = {s: np.array(raw[s]["disto"][:5]) for s in ("left", "right")}
    _, _, P1, P2, Q, _, _ = cv2.stereoRectify(K["left"], dist["left"], K["right"], dist["right"], (2208, 1242),
                                              np.array(raw["stereo_R"]), np.array(raw["stereo_T_mm"]).reshape(3, 1),
                                              flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
    assert np.allclose(P1, cal["P1"], atol=1e-9) and np.allclose(P2, cal["P2"], atol=1e-9)
    assert cal["fx"] == pytest.approx(P1[0, 0]) and cal["fx"] != pytest.approx(cal["sources"]["sdk_rectified"]["left"]["fx"])


def test_air_pairs_are_rectified_and_left_is_left():
    r = RECS["air"]
    f = r.n_frames - 1
    L = cv2.imread(str(r.left_path(f)), cv2.IMREAD_GRAYSCALE)
    R = cv2.imread(str(r.right_path(f)), cv2.IMREAD_GRAYSCALE)
    s = epipolar_dy(L, R)
    assert s["n"] >= 30
    assert s["frac_dx_pos"] > 0.95       # positive disparity: the top half of the stack is the left view
    assert abs(s["median_dy"]) < 4.0      # a ~2.5 px vertical residual was measured on 3 Nov; recorded, not corrected
