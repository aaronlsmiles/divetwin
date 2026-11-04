"""Camera poses. OpenCV convention (x right, y down, z forward); the world is the real camera's frame at
frame 0, in uncorrected stereo units. A pose maps camera-frame points to the world: x_w = c R x_c + C."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Pose:
    R: np.ndarray                                 # camera-to-world rotation
    C: np.ndarray                                 # camera centre in the world (su)
    c: float = 1.0                                # scale applied to camera-frame points (registration only)

    @classmethod
    def identity(cls) -> "Pose":
        return cls(np.eye(3), np.zeros(3), 1.0)

    def to_world(self, p_cam: np.ndarray) -> np.ndarray:
        return self.c * p_cam @ self.R.T + self.C

    def copy(self) -> "Pose":
        return Pose(self.R.copy(), self.C.copy(), float(self.c))

    def yaw_deg(self) -> float:
        f = self.R[:, 2]  # the camera's forward axis in the world
        return float(np.degrees(np.arctan2(f[0], f[2])))


def rot_y(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def so3_exp(w: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(w))
    Kx = np.array([[0.0, -w[2], w[1]], [w[2], 0.0, -w[0]], [-w[1], w[0], 0.0]])
    if th < 1e-12:
        return np.eye(3) + Kx
    return np.eye(3) + np.sin(th) / th * Kx + (1 - np.cos(th)) / th**2 * (Kx @ Kx)


def straight_path(n: int = 49, travel: float = 200.0, yaw_deg: float = 3.0) -> list[Pose]:
    """The self-test path: forward `travel` su over n frames with a +-yaw_deg sinusoidal yaw."""
    out = []
    for k in range(n):
        a = k / (n - 1)
        out.append(Pose(rot_y(np.deg2rad(yaw_deg) * np.sin(2 * np.pi * a)), np.array([0.0, 0.0, travel * a])))
    return out
