"""Audible alarm (winsound). The visual overlay popup lives in app.py because
it must run on the Tk main thread."""
from __future__ import annotations

import os
import sys
import threading


def play(sound_path: str | None) -> None:
    """Play the alarm sound asynchronously. Falls back to a system beep."""
    if sys.platform == "win32":
        _play_win(sound_path)
    else:  # pragma: no cover - app targets Windows
        sys.stdout.write("\a")
        sys.stdout.flush()


def _play_win(sound_path: str | None) -> None:
    import winsound
    if sound_path and os.path.isfile(sound_path):
        try:
            winsound.PlaySound(sound_path,
                               winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except Exception:
            pass
    # No custom sound configured / failed — three urgent beeps, off-thread.
    def _beep():
        try:
            for _ in range(3):
                winsound.Beep(880, 180)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass

    threading.Thread(target=_beep, daemon=True).start()
