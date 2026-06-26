"""Stage 1: OCR of the Local header count ("Local [8]").

Only an integer is extracted, which is near error-free. Degrades gracefully: if
Tesseract is not installed, ``available()`` is False and the scanner falls back
to Stage-2-only detection (colour sampling still works).
"""
from __future__ import annotations

import os
import re
from typing import Optional

import numpy as np

_COUNT_RE = re.compile(r"\[(\d+)\]")     # prefer the number inside brackets
_ANY_NUM_RE = re.compile(r"\d+")
_FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")   # "6/6" haven pocket counter

# Standard Windows install locations to fall back on when tesseract.exe isn't on
# PATH and no explicit path is configured.
_DEFAULT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
]

_configured = False
_available: Optional[bool] = None
resolved_cmd: Optional[str] = None  # the path that actually worked, for the UI


def _autodetect() -> Optional[str]:
    for p in _DEFAULT_PATHS:
        if p and os.path.isfile(p):
            return p
    return None


def configure(tesseract_cmd: Optional[str]) -> None:
    """Point pytesseract at tesseract.exe.

    Priority: explicit ``tesseract_cmd`` > whatever is already on PATH >
    auto-detected standard install location.
    """
    global _configured, _available, resolved_cmd
    try:
        import pytesseract
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            resolved_cmd = tesseract_cmd
        else:
            # If PATH lookup will fail, fall back to a standard install path.
            try:
                pytesseract.get_tesseract_version()
                resolved_cmd = pytesseract.pytesseract.tesseract_cmd
            except Exception:
                found = _autodetect()
                if found:
                    pytesseract.pytesseract.tesseract_cmd = found
                    resolved_cmd = found
    except Exception:
        pass
    _configured = True
    _available = None  # re-probe


def available() -> bool:
    global _available
    if _available is not None:
        return _available
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _available = True
    except Exception:
        _available = False
    return _available


def _preprocess(img_rgb: np.ndarray) -> "Image.Image":  # type: ignore[name-defined]
    """Prepare a tiny digit crop for OCR.

    Greyscale → 6x upscale → autocontrast → binarize to black-on-white → add a
    white border (quiet zone). The quiet zone and grayscale-first upscale matter
    a lot for small digits: without them strokes merge and a '0' is easily
    misread as '8'. Black-on-white matches Tesseract's training data.
    """
    from PIL import Image, ImageOps
    gray = (0.299 * img_rgb[:, :, 0] + 0.587 * img_rgb[:, :, 1]
            + 0.114 * img_rgb[:, :, 2]).astype(np.uint8)
    im = Image.fromarray(gray, mode="L")
    im = im.resize((im.width * 6, im.height * 6), Image.LANCZOS)
    im = ImageOps.autocontrast(im)
    arr = np.asarray(im)
    thr = max(80, int(arr.mean()))
    binar = np.where(arr > thr, 0, 255).astype(np.uint8)   # invert: light→black
    out = Image.fromarray(binar, mode="L")
    return ImageOps.expand(out, border=22, fill=255)


# psm modes voted over. The counter is a bare number / "N/M", so single-line,
# single-word and single-char segmentations all contribute a vote.
_PSMS = (7, 8, 6, 13, 11, 10)


def _digits(text: str) -> Optional[int]:
    """All digit characters in ``text`` as one integer (joins split tokens)."""
    ds = "".join(c for c in text if c.isdigit())
    return int(ds) if ds else None


def _majority(values: list) -> Optional[object]:
    if not values:
        return None
    from collections import Counter
    return Counter(values).most_common(1)[0][0]


def _ocr_text(img_rgb: np.ndarray) -> str:
    """Raw per-psm OCR of a digit region (digits whitelist). For debugging."""
    import pytesseract
    im = _preprocess(img_rgb)
    out = []
    for psm in _PSMS:
        txt = pytesseract.image_to_string(
            im, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789")
        out.append(f"psm{psm}:{txt.strip()!r}")
    return "  ".join(out)


def read_count(img_rgb: np.ndarray) -> Optional[int]:
    """Integer headcount from the header region, or None.

    Votes across several page-segmentation modes and returns the most common
    reading — robust against a single mode misreading e.g. '0' as '8'.
    """
    if not available():
        return None
    try:
        import pytesseract
        im = _preprocess(img_rgb)
        votes = []
        for psm in _PSMS:
            text = pytesseract.image_to_string(
                im, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789")
            n = _digits(text)
            if n is not None:
                votes.append(n)
        return _majority(votes)
    except Exception:
        return None


def read_line(img_rgb: np.ndarray) -> str:
    """OCR a single line of text (e.g. a pilot name). Best-effort, may contain
    errors on exotic EVE names — the threat-check tolerates unresolved names."""
    if not available():
        return ""
    try:
        import pytesseract
        im = _preprocess(img_rgb)
        # psm 7 = single text line; default charset (names have letters/digits/'-)
        txt = pytesseract.image_to_string(im, config="--psm 7")
        return " ".join(txt.split()).strip()
    except Exception:
        return ""


def read_fraction(img_rgb: np.ndarray) -> Optional["tuple[int, int]"]:
    """Read an "N/M" counter (e.g. the Haven pocket counter "6/6").

    Returns ``(current, total)`` or None. The region should be drawn tightly
    around the number, excluding any progress bar.
    """
    if not available():
        return None
    try:
        import pytesseract
        im = _preprocess(img_rgb)
        slash_votes = []     # proper "N/M"
        sep_votes = []       # two numbers, any separator (slash misread)
        twin_votes = []      # "NN" with no separator → likely N/N (slash lost)
        for psm in _PSMS:
            cfg_w = f"--psm {psm} -c tessedit_char_whitelist=0123456789/"
            t = pytesseract.image_to_string(im, config=cfg_w)
            m = _FRACTION_RE.search(t)
            if m and int(m.group(2)) > 0:
                slash_votes.append((int(m.group(1)), int(m.group(2))))
                continue
            # no slash recognised — try without the whitelist, tolerant separator
            t2 = pytesseract.image_to_string(im, config=f"--psm {psm}")
            m2 = re.search(r"(\d+)\s*\D+\s*(\d+)", t2)
            if m2 and int(m2.group(2)) > 0:
                sep_votes.append((int(m2.group(1)), int(m2.group(2))))
                continue
            # last resort: a bare run of digits (slash dropped entirely)
            digits = "".join(c for c in t if c.isdigit())
            if len(digits) == 2 and digits[0] == digits[1]:   # "66" → 6/6
                twin_votes.append((int(digits[0]), int(digits[1])))
        return _majority(slash_votes or sep_votes or twin_votes)
    except Exception:
        return None


def read_fraction_text(img_rgb: np.ndarray) -> str:
    """Raw OCR of the haven counter region. For debugging — shows both the
    digits+slash pass and the unrestricted pass so a lost slash is visible."""
    if not available():
        return "OCR aus"
    import pytesseract
    im = _preprocess(img_rgb)
    out = []
    for psm in (7, 8, 6):
        w = pytesseract.image_to_string(
            im, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789/").strip()
        full = pytesseract.image_to_string(im, config=f"--psm {psm}").strip()
        out.append(f"psm{psm}: slash={w!r} frei={full!r}")
    return "  ".join(out)
