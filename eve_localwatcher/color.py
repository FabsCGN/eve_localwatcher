"""Colour features, distance and the friendly-whitelist test.

Colours are compared in an HSV-derived feature space that behaves well for
EVE's standing tags:

    x = saturation * cos(2*pi*hue)
    y = saturation * sin(2*pi*hue)
    z = value

Chromatic tags (purple/green/blue/red/orange) separate cleanly by hue, while
achromatic pixels (grey/white/empty dark slot) collapse near the value axis so
hue noise on near-grey pixels doesn't cause false matches. Distance is plain
Euclidean in this space, scaled to roughly 0..173 so a single ``tolerance``
threshold is intuitive.
"""
from __future__ import annotations

import colorsys
import math
from typing import Iterable, List, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]
_SCALE = 100.0


def rgb_to_feature(rgb: Sequence[float]) -> Tuple[float, float, float]:
    r, g, b = (float(rgb[0]) / 255.0, float(rgb[1]) / 255.0, float(rgb[2]) / 255.0)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (s * math.cos(2 * math.pi * h), s * math.sin(2 * math.pi * h), v)


def color_distance(c1: Sequence[float], c2: Sequence[float]) -> float:
    f1 = rgb_to_feature(c1)
    f2 = rgb_to_feature(c2)
    return _SCALE * math.sqrt(sum((a - b) ** 2 for a, b in zip(f1, f2)))


def is_friendly(rgb: RGB, friendly_colors: Iterable[RGB], tolerance: float) -> bool:
    """True if ``rgb`` is within ``tolerance`` of any calibrated friendly colour."""
    return any(color_distance(rgb, fc) <= tolerance for fc in friendly_colors)


def has_tag(rgb: RGB, min_value: int) -> bool:
    """True if the slot actually shows a coloured standing tag (vs. an empty /
    dark background slot).

    EVE renders tags as bright/saturated icons on a dark panel; an empty slot is
    just the dark background. The brightest channel (HSV 'value') cleanly
    separates the two: empty slots sit far below ``min_value``, real tags far
    above it.
    """
    return max(int(rgb[0]), int(rgb[1]), int(rgb[2])) >= min_value


# Per-row classification result.
FRIENDLY = "friendly"
THREAT = "threat"
EMPTY = "empty"        # no tag present — ignored, never alarms


def classify(rgb: RGB, friendly_colors: Iterable[RGB], tolerance: float,
             min_value: int) -> str:
    """Classify an icon-slot colour.

    Only a present, non-friendly tag is a THREAT. An empty/dark slot is EMPTY
    and never alarms — this is what stops phantom alarms on the dark background
    when the captured row shifts (e.g. when multiboxing / switching clients).
    """
    if not has_tag(rgb, min_value):
        return EMPTY
    return FRIENDLY if is_friendly(rgb, friendly_colors, tolerance) else THREAT


def median_color(patch: np.ndarray) -> RGB:
    """Median RGB of an HxWx3 patch (robust to anti-aliasing / sub-pixel edges)."""
    flat = patch.reshape(-1, 3)
    med = np.median(flat, axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


def bucket(rgb: RGB, step: int = 24) -> RGB:
    """Coarse colour bucket, used to debounce 'same threat' across ticks."""
    return (int(rgb[0]) // step, int(rgb[1]) // step, int(rgb[2]) // step)


def dedupe_colors(colors: Iterable[RGB], tolerance: float) -> List[RGB]:
    """Drop near-duplicate colours so the friendly set stays small."""
    out: List[RGB] = []
    for c in colors:
        if not any(color_distance(c, k) <= tolerance for k in out):
            out.append(c)
    return out
