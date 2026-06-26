"""Windows helpers: DPI awareness, window lookup, virtual-screen geometry.

Everything degrades gracefully if pywin32 / ctypes are unavailable so the rest
of the app still runs (just without window-relative capture).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

try:
    import win32gui  # type: ignore
    HAVE_WIN32 = True
except Exception:  # pragma: no cover - non-Windows / missing pywin32
    HAVE_WIN32 = False


def set_dpi_aware() -> None:
    """Make this process per-monitor DPI aware.

    Without this, Tk, win32gui and mss can disagree about pixel coordinates
    under display scaling, so the selected region and the captured region drift
    apart. Must be called once, before creating any Tk window or capturing.
    """
    try:
        import ctypes
        try:
            # PROCESS_PER_MONITOR_DPI_AWARE = 2 (Win 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()  # Vista+ fallback
    except Exception:
        pass


def virtual_screen() -> Tuple[int, int, int, int]:
    """(left, top, width, height) of the whole virtual desktop (all monitors)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        return (u.GetSystemMetrics(SM_XVIRTUALSCREEN),
                u.GetSystemMetrics(SM_YVIRTUALSCREEN),
                u.GetSystemMetrics(SM_CXVIRTUALSCREEN),
                u.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    except Exception:
        return (0, 0, 0, 0)


def list_windows(title_substring: str) -> List[Tuple[int, str]]:
    """Visible top-level windows whose title contains ``title_substring``."""
    if not HAVE_WIN32:
        return []
    needle = title_substring.lower()
    found: List[Tuple[int, str]] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title and needle in title.lower():
            found.append((hwnd, title))

    win32gui.EnumWindows(_cb, None)
    return found


def find_window_origin(title_substring: str) -> Optional[Tuple[int, int]]:
    """Top-left (left, top) of the first matching window, or None."""
    rect = find_window_rect(title_substring)
    return (rect[0], rect[1]) if rect else None


def find_window_rect(title_substring: str) -> Optional[Tuple[int, int, int, int]]:
    """(left, top, right, bottom) of the first matching window, or None."""
    matches = list_windows(title_substring)
    if not matches:
        return None
    hwnd = matches[0][0]
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
