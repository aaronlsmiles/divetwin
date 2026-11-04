"""Seven-parameter registration: rotation, camera centre and one scale, by robust point-to-plane ICP.

Open3D 0.20.0 has no estimator that does both: TransformationEstimationPointToPoint(with_scaling=True)
fits scale but takes no robust kernel; TransformationEstimationPointToPlane(kernel) takes a Huber
kernel but fixes scale at 1 (both checked on the 0.20.0 wheel). So this module solves the 7-DoF
Gauss-Newton step itself: residual e_i = n_i . (c R p_i + C - q_i) / z_i (relative to the point's
depth, the AbsRel convention), Huber-weighted, with nearest-vertex correspondences from a KD-tree."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.spatial import cKDTree

from camera import Pose, so3_exp

SCHEDULE = ((0.30, 10), (0.15, 10), (0.08, 15))  # (correspondence gate relative to depth, iterations)
HUBER_K = 0.03                                   # relative residual where Huber turns linear
FIT_TOL = 0.05                                   # |relative residual| counted as a fit for `fitness`
MIN_CORR = 200


@dataclass
class IcpResult:
    pose: Pose
    fitness: float      # share of source points within FIT_TOL relative residual of the surface
    rmse: float         # RMS relative residual over those points
    n_corr: int
    iters: int
    history: list = field(default_factory=list)


class Target:
    """The tank surface for registration: vertices with normals, in a KD-tree."""

    def __init__(self, pts: np.ndarray, nrm: np.ndarray):
        ok = np.all(np.isfinite(pts), axis=1) & np.all(np.isfinite(nrm), axis=1)
        self.pts, self.nrm = pts[ok], nrm[ok]
        self.tree = cKDTree(self.pts)


def register(src: np.ndarray, target: Target, init: Pose, schedule=SCHEDULE, huber_k: float = HUBER_K) -> IcpResult:
    """src: (N, 3) camera-frame points of one generated frame. Returns the similarity that best lays
    them on the tank surface, started from `init` (the previous frame's pose)."""
    pose = init.copy()
    z = src[:, 2]
    it = 0
    hist = []
    for gate, n_it in schedule:
        for _ in range(n_it):
            it += 1
            Y = pose.to_world(src)
            dist, j = target.tree.query(Y, k=1, workers=-1)
            q, n = target.pts[j], target.nrm[j]
            ok = dist < gate * z
            if np.count_nonzero(ok) < MIN_CORR:
                break
            Yo, qo, no, zo = Y[ok], q[ok], n[ok], z[ok]
            a = Yo - pose.C
            e = np.sum((Yo - qo) * no, axis=1) / zo
            J = np.concatenate([np.cross(a, no), no, np.sum(no * a, axis=1, keepdims=True)], axis=1) / zo[:, None]
            ae = np.abs(e)
            w = np.where(ae <= huber_k, 1.0, huber_k / np.maximum(ae, 1e-300))
            H = J.T @ (J * w[:, None])
            g = J.T @ (w * e)
            H += np.eye(7) * (1e-9 * np.trace(H) / 7 + 1e-12)
            x = -np.linalg.solve(H, g)
            pose = Pose(so3_exp(x[:3]) @ pose.R, pose.C + x[3:6], pose.c * float(np.exp(x[6])))
            hist.append(float(np.sqrt(np.mean(w * e**2))))
            if np.linalg.norm(x[:3]) < 1e-7 and np.linalg.norm(x[3:6]) < 1e-5 * np.median(z) and abs(x[6]) < 1e-7:
                break
    Y = pose.to_world(src)
    dist, j = target.tree.query(Y, k=1, workers=-1)
    e = np.sum((Y - target.pts[j]) * target.nrm[j], axis=1) / z
    fit = (dist < schedule[-1][0] * z) & (np.abs(e) < FIT_TOL)
    n_fit = int(np.count_nonzero(fit))
    rmse = float(np.sqrt(np.mean(e[fit] ** 2))) if n_fit else float("nan")
    return IcpResult(pose, n_fit / max(len(src), 1), rmse, n_fit, it, hist)


# ---- second estimator: image tracks against the reconstruction (perspective-n-point) ----------------

LK = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
FB_MAX = 1.0      # px, forward-backward tracking error allowed
MIN_TRACKS = 30
RESEED_BELOW = 150


def _seed(gray: np.ndarray, ok: np.ndarray, existing: np.ndarray, n: int = 400) -> np.ndarray:
    mask = ok.astype(np.uint8) * 255
    for x, y in existing.reshape(-1, 2):
        cv2.circle(mask, (int(round(x)), int(round(y))), 10, 0, -1)
    pts = cv2.goodFeaturesToTrack(gray, maxCorners=n, qualityLevel=0.005, minDistance=10, mask=mask)
    return np.zeros((0, 2), np.float32) if pts is None else pts.reshape(-1, 2).astype(np.float32)


def _on_mask(pts: np.ndarray, mask: np.ndarray, tracked: np.ndarray | None = None) -> np.ndarray:
    """Which points (x, y) fall on a True pixel of `mask`. Points off the image, points the tracker did not
    follow (`tracked` False: their coordinates may be NaN) and non-finite points count as off the mask;
    only tracked, finite points are rounded to pixels."""
    use = np.isfinite(pts).all(axis=1) if tracked is None else tracked & np.isfinite(pts).all(axis=1)
    out = np.zeros(len(pts), bool)
    p = pts[use]
    u = np.rint(p[:, 0]).astype(int)
    v = np.rint(p[:, 1]).astype(int)
    inside = (u >= 0) & (u < mask.shape[1]) & (v >= 0) & (v < mask.shape[0])
    hit = np.zeros(len(p), bool)
    hit[inside] = mask[v[inside], u[inside]]
    out[use] = hit
    return out


def _lift(pts: np.ndarray, inv_depth: np.ndarray, k, pose: Pose) -> tuple[np.ndarray, np.ndarray]:
    """Pixels with a rendered (or measured) inverse depth -> world points; returns (points, kept)."""
    u = np.clip(np.rint(pts[:, 0]).astype(int), 0, k.width - 1)
    v = np.clip(np.rint(pts[:, 1]).astype(int), 0, k.height - 1)
    w = inv_depth[v, u]
    keep = np.isfinite(w) & (w > 0)
    z = 1.0 / w[keep]
    p_cam = np.stack([(pts[keep, 0] - k.cx) * z / k.fx, (pts[keep, 1] - k.cy) * z / k.fy, z], axis=-1)
    return p_cam @ pose.R.T + pose.C, keep


def track_path(frames: list[np.ndarray], k, inv_depth0: np.ndarray, render_inv=None, valid0=None,
               moving: np.ndarray | None = None) -> list[dict]:
    """Camera path of a clip from its images alone: features seeded on frame 0 get their 3D from the
    tank (inv_depth0, same grid as the frames), are tracked frame to frame (pyramidal Lucas-Kanade with a
    forward-backward check), and each frame's pose is a RANSAC PnP against those 3D points. When tracks
    run low, new ones are seeded and lifted to 3D with `render_inv(pose)` (the tank rendered from the
    current estimate). `moving` (N, H, W) bool marks pixels of anything tracked as moving: no track is
    seeded there, and a track whose position falls inside it is dropped on that frame.
    Returns per frame {pose, n_tracks, n_inliers, reproj_px, lost}."""
    Kmat = k.K()
    gray0 = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY) if frames[0].ndim == 3 else frames[0]
    ok0 = np.isfinite(inv_depth0) if valid0 is None else valid0
    if moving is not None:
        assert moving.shape == (len(frames),) + gray0.shape, "moving must be (N, H, W) on the frames' grid"
        ok0 = ok0 & ~moving[0]
    pts = _seed(gray0, ok0, np.zeros((0, 2)))
    X, keep = _lift(pts, inv_depth0, k, Pose.identity())
    pts = pts[keep]
    out = [{"pose": Pose.identity(), "n_tracks": int(len(pts)), "n_inliers": int(len(pts)), "reproj_px": 0.0, "lost": False}]
    prev, pose, lost = gray0, Pose.identity(), False
    for i, f in enumerate(frames[1:], start=1):
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f
        if lost or len(pts) < MIN_TRACKS:
            lost = True
            out.append({"pose": pose.copy(), "n_tracks": 0, "n_inliers": 0, "reproj_px": float("nan"), "lost": True})
            continue
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, gray, pts.reshape(-1, 1, 2), None, **LK)
        back, st2, _ = cv2.calcOpticalFlowPyrLK(gray, prev, nxt, None, **LK)
        fb = np.linalg.norm(back.reshape(-1, 2) - pts, axis=1)
        good = (st.ravel() == 1) & (st2.ravel() == 1) & (fb < FB_MAX)
        if moving is not None:
            good &= ~_on_mask(nxt.reshape(-1, 2), moving[i], tracked=st.ravel() == 1)
        pts, X = nxt.reshape(-1, 2)[good], X[good]
        if len(pts) < MIN_TRACKS:
            lost = True
            out.append({"pose": pose.copy(), "n_tracks": int(len(pts)), "n_inliers": 0, "reproj_px": float("nan"), "lost": True})
            continue
        rvec0, _ = cv2.Rodrigues(pose.R.T)
        tvec0 = -pose.R.T @ pose.C
        okp, rvec, tvec, inl = cv2.solvePnPRansac(X, pts, Kmat, None, rvec0.copy(), tvec0.reshape(3, 1).copy(),
                                                  useExtrinsicGuess=True, iterationsCount=200,
                                                  reprojectionError=2.0, confidence=0.999,
                                                  flags=cv2.SOLVEPNP_ITERATIVE)
        if not okp or inl is None or len(inl) < MIN_TRACKS // 2:
            lost = True
            out.append({"pose": pose.copy(), "n_tracks": int(len(pts)), "n_inliers": 0, "reproj_px": float("nan"), "lost": True})
            continue
        inl = inl.ravel()
        rvec, tvec = cv2.solvePnPRefineLM(X[inl], pts[inl], Kmat, None, rvec, tvec)
        Rcw, _ = cv2.Rodrigues(rvec)  # world -> camera
        pose = Pose(Rcw.T, (-Rcw.T @ tvec).ravel(), 1.0)
        proj, _ = cv2.projectPoints(X[inl], rvec, tvec, Kmat, None)
        err = float(np.median(np.linalg.norm(proj.reshape(-1, 2) - pts[inl], axis=1)))
        out.append({"pose": pose.copy(), "n_tracks": int(len(pts)), "n_inliers": int(len(inl)), "reproj_px": err, "lost": False})
        pts, X = pts[inl], X[inl]
        if len(pts) < RESEED_BELOW and render_inv is not None:
            rinv = render_inv(pose)
            ok = np.isfinite(rinv) if moving is None else np.isfinite(rinv) & ~moving[i]
            new = _seed(gray, ok, pts)
            Xn, kn = _lift(new, rinv, k, pose)
            pts, X = np.concatenate([pts, new[kn]]), np.concatenate([X, Xn])
        prev = gray
    return out
