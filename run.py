"""Top-level entry point for packaging (PyInstaller) and direct execution.

Uses an absolute import so it works both as a frozen .exe and as
``python run.py`` (unlike ``eve_localwatcher/__main__.py``, which relies on
package-relative imports).
"""
from eve_localwatcher.__main__ import main

if __name__ == "__main__":
    main()
