"""Application entry point for 24-Hour Screentime & Login Session Clock.

Coordinates application initialization, library preloading, and lifecycle.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from PyQt6.QtWidgets import QApplication

# Ensure local directories are in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure bundled libxcb-cursor0 is loaded directly before PyQt6 initialization
LIB_FILE = BASE_DIR / "lib" / "usr" / "lib" / "x86_64-linux-gnu" / "libxcb-cursor.so.0"
if LIB_FILE.exists():
    try:
        import ctypes
        ctypes.cdll.LoadLibrary(str(LIB_FILE))
    except Exception as exc:
        print(f"Notice: bundled libxcb-cursor load note: {exc}")

from config import config
from gui.desktop_widget import ScreentimeDesktopWidget


def main() -> None:
    """Launch the 24-Hour Screentime Clock desktop widget application."""
    app = QApplication(sys.argv)
    app.setApplicationName("24H Screentime Clock")

    widget = ScreentimeDesktopWidget()
    widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
