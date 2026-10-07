"""Video frame access (OpenCV) with cheap JPEG/base64 encoding for VLM calls."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import List, Optional, Sequence

import cv2
import numpy as np


@dataclass
class VideoInfo:
    path: str
    fps: float
    n_frames: int
    width: int
    height: int

    @property
    def duration(self) -> float:
        return self.n_frames / self.fps if self.fps else 0.0


class VideoReader:
    """Random-access frame reader. One instance per video; not thread-safe."""

    def __init__(self, path: str):
        self.path = path
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"cannot open video {path}")
        self.info = VideoInfo(
            path=path,
            fps=float(self._cap.get(cv2.CAP_PROP_FPS) or 30.0),
            n_frames=int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    @property
    def duration(self) -> float:
        return self.info.duration

    def frame_at(self, t: float) -> Optional[np.ndarray]:
        """BGR frame nearest to time t (seconds), or None past the end."""
        t = min(max(0.0, t), max(0.0, self.duration - 1.0 / self.info.fps))
        idx = int(round(t * self.info.fps))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = self._cap.read()
        return frame if ok else None

    def frames_at(self, times: Sequence[float]) -> List[Optional[np.ndarray]]:
        return [self.frame_at(t) for t in times]

    def close(self) -> None:
        self._cap.release()

    def __enter__(self) -> "VideoReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def resize_long_edge(frame: np.ndarray, long_edge: int = 512) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = long_edge / float(max(h, w))
    if scale >= 1.0:
        return frame
    return cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)


def to_jpeg_bytes(frame: np.ndarray, long_edge: int = 512, quality: int = 80) -> bytes:
    fr = resize_long_edge(frame, long_edge)
    ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def to_jpeg_b64(frame: np.ndarray, long_edge: int = 512, quality: int = 80) -> str:
    return base64.b64encode(to_jpeg_bytes(frame, long_edge, quality)).decode("ascii")


def sample_times(start: float, end: float, n: int, margin_frac: float = 0.1) -> List[float]:
    """n evenly spaced times inside [start, end], keeping a margin from the boundaries."""
    if n <= 0 or end <= start:
        return []
    span = end - start
    lo, hi = start + margin_frac * span, end - margin_frac * span
    if n == 1:
        return [0.5 * (lo + hi)]
    return [lo + i * (hi - lo) / (n - 1) for i in range(n)]


def laplacian_sharpness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
