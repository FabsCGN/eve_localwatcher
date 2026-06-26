"""Entry point: ``python -m eve_localwatcher``."""
from __future__ import annotations

from . import winutil


def main() -> None:
    # Must run before any Tk window or screen capture so coordinates agree
    # across Tk, win32gui and mss under display scaling.
    winutil.set_dpi_aware()
    from .app import App
    App().run()


if __name__ == "__main__":
    main()
