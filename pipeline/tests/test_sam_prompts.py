"""Call 39 (3 Nov): SAM 2 prompts can carry later-frame boxes and positive/negative points, and a negative-only
prompt is applied as a refinement after a first propagation. Driven here with a fake predictor."""
import numpy as np
import pytest

import modal_depth


class _Logits:
    def __init__(self, v):
        self.v = v

    def __getitem__(self, k):
        return _Logits(self.v[k])

    def __gt__(self, other):
        return _Logits(self.v > other)

    def cpu(self):
        return self

    def numpy(self):
        return self.v


class FakePredictor:
    """Records the calls; every propagated frame gets an all-ones mask for each object."""

    def __init__(self, n, h=4, w=6):
        self.calls, self.n, self.h, self.w = [], n, h, w
        self.ids = []
        self.add_all_frames_to_correct_as_cond = False

    def add_new_points_or_box(self, state, frame_idx, obj_id, **kw):
        self.calls.append(("add", frame_idx, obj_id, sorted(kw), self.add_all_frames_to_correct_as_cond))
        if obj_id not in self.ids:
            self.ids.append(obj_id)

    def propagate_in_video(self, state, start_frame_idx, reverse):
        self.calls.append(("prop", start_frame_idx, reverse))
        frames = range(start_frame_idx, -1, -1) if reverse else range(start_frame_idx, self.n)
        for fi in frames:
            yield fi, list(self.ids), _Logits(np.ones((len(self.ids), 1, self.h, self.w), bool))


def test_prompt_to_half_halves_boxes_and_points_and_drops_the_reason():
    p = {"frame": 7, "obj": "hand", "box": [10, 20, 30, 40], "points": [[100, 50], [8, 6]], "labels": [1, 0], "reason": "x"}
    assert modal_depth.prompt_to_half(p) == {"frame": 7, "obj": "hand", "box": [5.0, 10.0, 15.0, 20.0],
                                             "points": [[50.0, 25.0], [4.0, 3.0]], "labels": [1, 0]}
    assert modal_depth.prompt_to_half({"frame": 1, "obj": "bottle", "box": [2, 2, 4, 4]}) == \
        {"frame": 1, "obj": "bottle", "box": [1.0, 1.0, 2.0, 2.0]}


def test_split_puts_boxes_and_positive_points_first_and_negative_only_prompts_after():
    a = {"frame": 5, "obj": "bottle", "box": [1, 1, 3, 3]}
    b = {"frame": 9, "obj": "bottle", "points": [[1, 1]], "labels": [0]}
    c = {"frame": 3, "obj": "bottle", "points": [[1, 1], [2, 2]], "labels": [0, 1]}
    d = {"frame": 2, "obj": "bottle", "points": [[1, 1]], "labels": [0]}
    cond, refine = modal_depth.split_prompts([a, b, c, d])
    assert cond == [a, c] and refine == [d, b]            # refinements sorted by frame


def test_drive_adds_conditioning_prompts_first_then_refines_and_repropagates_from_the_refinement():
    pred = FakePredictor(12)
    prompts = [{"frame": 4, "obj": "bottle", "box": [1, 1, 3, 3]},
               {"frame": 4, "obj": "hand", "box": [1, 1, 3, 3]},
               {"frame": 8, "obj": "hand", "box": [1, 1, 3, 3]},
               {"frame": 9, "obj": "bottle", "points": [[2, 2]], "labels": [0]}]
    out = modal_depth.drive_sam2(pred, {}, prompts, 12, 4, 6)
    kinds = [c[0] for c in pred.calls]
    assert kinds == ["add", "add", "add", "prop", "prop", "add", "prop"]
    assert pred.calls[3] == ("prop", 4, False) and pred.calls[4] == ("prop", 4, True)
    # SAM 2 recomputes every non-conditioning frame on each propagation, so a correction only survives if the
    # corrected frame is a conditioning frame: the flag is on for the refinement and off for the first pass
    assert pred.calls[5] == ("add", 9, 1, ["labels", "points"], True) and pred.calls[6] == ("prop", 9, False)
    assert pred.calls[0][3] == ["box"] and pred.calls[0][4] is False and pred.calls[2][:3] == ("add", 8, 2)
    assert set(out) == {"bottle", "hand"} and out["bottle"].shape == (12, 4, 6) and out["bottle"].all()


def test_drive_without_a_conditioning_prompt_refuses():
    with pytest.raises(ValueError):
        modal_depth.drive_sam2(FakePredictor(5), {}, [{"frame": 2, "obj": "bottle", "points": [[1, 1]], "labels": [0]}], 5, 4, 6)


def test_run_masks_sends_half_resolution_prompts_with_points(tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setenv("DIVETWIN_RUNS", str(tmp_path / "runs"))
    from test_modal_helpers import _DepthRec, _npy, _Remote
    monkeypatch.setattr(modal_depth, "Sam2Video", lambda: type("S", (), {"track": _Remote(
        lambda frames, prompts: (sent.update(p=prompts) or {"bottle": _npy(np.packbits(np.ones((len(frames), 621, 1104), bool), axis=-1))}, 1.0))})())
    monkeypatch.setattr(modal_depth, "fetch_weights", _Remote(lambda *a, **k: None))
    recs = {"a": _DepthRec(tmp_path, "a", n_frames=3)}
    monkeypatch.setattr("recordings.recordings", lambda: recs)
    monkeypatch.setattr(modal_depth, "_seeds", lambda: {"a": [
        {"frame": 0, "obj": "bottle", "box": [10, 20, 30, 40]},
        {"frame": 2, "obj": "bottle", "points": [[8, 6]], "labels": [0], "reason": "ripple"}]})
    modal_depth.run_masks()
    assert sent["p"] == [{"frame": 0, "obj": "bottle", "box": [5.0, 10.0, 15.0, 20.0]},
                         {"frame": 2, "obj": "bottle", "points": [[4.0, 3.0]], "labels": [0]}]
