"""Audible alarm with per-alert volume — no third-party dependency.

``winsound`` cannot set a volume, so we read the WAV with the stdlib ``wave``
module, scale the PCM samples by the requested volume (numpy is already a
dependency) and play the result from memory with ``SND_MEMORY``. Keeping this
dependency-free avoids enlarging the packaged .exe and the extra heuristic
surface an audio library would add.

Degrades gracefully: non-PCM/exotic WAVs play unscaled, and any failure (or no
custom WAV) falls back to a winsound beep. Like the previous implementation,
playback is single-voice — a new alarm replaces one still playing."""
from __future__ import annotations

import io
import os
import sys
import threading
import wave

import numpy as np

# path -> (wave params, samples ndarray, sampwidth) | None  (None = undecodable)
_orig_cache: dict = {}
# Keep a reference to the buffer currently handed to SND_ASYNC so it is not
# garbage-collected while Windows is still reading from it.
_live_buf: "bytes | None" = None


def play(sound_path: str | None, volume: float = 1.0) -> None:
    """Play the alarm asynchronously at ``volume`` (0.0..1.0).

    Falls back to a system beep when no custom WAV is set or playback fails.
    """
    vol = max(0.0, min(1.0, float(volume)))
    if sound_path and os.path.isfile(sound_path):
        data = _scaled_wav_bytes(sound_path, vol)
        if data is not None and _play_memory(data):
            return
    _fallback_beep()


def _load(path: str):
    """Decode and cache a WAV's params + samples. Returns the cache entry."""
    if path in _orig_cache:
        return _orig_cache[path]
    entry = None
    try:
        with wave.open(path, "rb") as w:
            params = w.getparams()
            frames = w.readframes(w.getnframes())
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(params.sampwidth)
        samples = np.frombuffer(frames, dtype=dtype) if dtype is not None else None
        entry = (params, samples, params.sampwidth)
    except Exception:
        entry = None
    _orig_cache[path] = entry
    return entry


def _scaled_wav_bytes(path: str, vol: float) -> "bytes | None":
    entry = _load(path)
    if entry is None:
        return None
    params, samples, sampwidth = entry
    try:
        if samples is None:              # unknown sample width → play unscaled
            with wave.open(path, "rb") as w:
                return _rebuild(params, w.readframes(w.getnframes()))
        if sampwidth == 1:               # 8-bit PCM is unsigned, centred at 128
            centred = samples.astype(np.int16) - 128
            out = np.clip(centred * vol + 128, 0, 255).astype(np.uint8)
        else:
            info = np.iinfo(samples.dtype)
            out = np.clip(samples.astype(np.float64) * vol,
                          info.min, info.max).astype(samples.dtype)
        return _rebuild(params, out.tobytes())
    except Exception:
        return None


def _rebuild(params, frame_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setparams(params)
        w.writeframes(frame_bytes)
    return buf.getvalue()


def _play_memory(wav_bytes: bytes) -> bool:
    global _live_buf
    if sys.platform != "win32":  # pragma: no cover - app targets Windows
        return False
    try:
        import winsound
        _live_buf = wav_bytes     # keep alive for the duration of async playback
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


def _fallback_beep() -> None:
    """Three urgent beeps off-thread. No volume control (winsound limitation)."""
    if sys.platform != "win32":  # pragma: no cover - app targets Windows
        sys.stdout.write("\a")
        sys.stdout.flush()
        return

    def _beep():
        import winsound
        try:
            for _ in range(3):
                winsound.Beep(880, 180)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass

    threading.Thread(target=_beep, daemon=True).start()
