"""Tail EVE chat log files (intel channels).

EVE writes one UTF-16-LE text file per channel per logged-in character under
``Documents\\EVE\\logs\\Chatlogs`` — where "Documents" is frequently
OneDrive-redirected (e.g. ``C:\\Users\\x\\OneDrive\\Dokumente``), so the
directory is resolved via the Windows shell first, with common fallbacks.

``ChatlogTail`` follows the newest file of one channel: it starts at EOF
(only NEW intel matters), decodes appended bytes, buffers partial lines, and
hops onto a newer file when one appears (client restart / next session).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional


def documents_dir() -> Optional[Path]:
    """The user's real Documents folder via the Windows shell (handles
    OneDrive redirection); None if that fails (non-Windows, odd setups)."""
    try:
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                        ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                   (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03,
                                        0x69, 0xC7))
        buf = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
            p = Path(buf.value)
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return p
    except Exception:
        pass
    return None


def candidate_log_dirs(override: Optional[str] = None) -> List[Path]:
    out: List[Path] = []
    if override:
        out.append(Path(override))
    docs = documents_dir()
    if docs:
        out.append(docs / "EVE" / "logs" / "Chatlogs")
    home = Path.home()
    for d in ("OneDrive/Dokumente", "OneDrive/Documents", "Documents",
              "Dokumente"):
        out.append(home / d / "EVE" / "logs" / "Chatlogs")
    return out


def find_chatlog_dir(override: Optional[str] = None) -> Optional[Path]:
    for d in candidate_log_dirs(override):
        try:
            if d.is_dir():
                return d
        except OSError:
            continue
    return None


def newest_channel_file(dirpath: Path, channel: str) -> Optional[Path]:
    """Newest logfile of the channel (pattern ``<Channel>_*.txt``)."""
    try:
        files = list(dirpath.glob(f"{channel}_*.txt"))
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


class ChatlogTail:
    RECHECK_S = 30.0     # how often to look for a newer file

    def __init__(self, dirpath: Path, channel: str) -> None:
        self._dir = dirpath
        self._channel = channel
        self._file: Optional[Path] = None
        self._pos = 0
        self._buf = b""
        self._next_recheck = 0.0
        self._open_newest(seek_end=True)

    @property
    def current_file(self) -> Optional[Path]:
        return self._file

    def _open_newest(self, seek_end: bool) -> None:
        f = newest_channel_file(self._dir, self._channel)
        if f is None or f == self._file:
            return
        self._file = f
        self._buf = b""
        try:
            self._pos = f.stat().st_size if seek_end else 0
        except OSError:
            self._pos = 0

    def poll(self) -> List[str]:
        """New complete decoded lines since the last poll (may be empty)."""
        now = time.monotonic()
        if now >= self._next_recheck:
            self._next_recheck = now + self.RECHECK_S
            # a newer file (relog, new session) starts fresh with only the
            # MOTD header — read it from the top so nothing is missed
            self._open_newest(seek_end=False)
        if self._file is None:
            return []
        try:
            size = self._file.stat().st_size
            if size < self._pos:            # truncated/replaced → restart
                self._pos = 0
                self._buf = b""
            if size == self._pos:
                return []
            with open(self._file, "rb") as fh:
                fh.seek(self._pos)
                chunk = fh.read(size - self._pos)
                self._pos = fh.tell()
        except OSError:
            return []
        self._buf += chunk
        # keep an even byte count — UTF-16 code units are 2 bytes
        cut = len(self._buf) - (len(self._buf) % 2)
        text = self._buf[:cut].decode("utf-16-le", errors="ignore")
        self._buf = self._buf[cut:]
        if "\n" not in text:
            # stash undecoded remainder back as bytes for the next poll
            self._buf = text.encode("utf-16-le") + self._buf
            return []
        head, tail = text.rsplit("\n", 1)
        self._buf = tail.encode("utf-16-le") + self._buf
        lines = [l.strip("\r﻿ \t") for l in head.split("\n")]
        return [l for l in lines if l]
