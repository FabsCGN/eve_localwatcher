"""Screen capture via mss.

``mss`` objects are not safe to share across threads, so a ``Capturer`` is
created inside the thread that uses it (the scan worker, and the Tk thread for
calibration previews).
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from .config import RegionTuple


class Capturer:
    def __init__(self) -> None:
        import mss
        self._sct = mss.mss()

    def grab(self, region_abs: RegionTuple) -> np.ndarray:
        """Grab an absolute (x, y, w, h) screen region as an RGB uint8 array."""
        x, y, w, h = region_abs
        monitor = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        raw = self._sct.grab(monitor)
        # mss returns BGRA; drop alpha and flip to RGB.
        arr = np.asarray(raw, dtype=np.uint8)[:, :, :3][:, :, ::-1]
        return np.ascontiguousarray(arr)

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass


def grab_once(region_abs: RegionTuple) -> np.ndarray:
    """Convenience one-shot grab (creates and disposes its own Capturer)."""
    cap = Capturer()
    try:
        return cap.grab(region_abs)
    finally:
        cap.close()
