"""Double-click launcher (no terminal window) — requires Python installed.

`.pyw` files run with pythonw.exe, so no console pops up. This is the
no-build option; for a standalone .exe (no Python needed) use build_exe.ps1.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eve_localwatcher.__main__ import main

main()
