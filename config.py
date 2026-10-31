"""Configuration and path settings for the 24-Hour Analog Screentime Clock.

Manages persistent file paths, library discovery for X11 cursor plugins,
and user interface customization parameters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Base application directory paths
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
CONFIG_FILE = DATA_DIR / "widget_config.json"
HISTORY_FILE = DATA_DIR / "screentime_history.json"
LIB_PATH = APP_DIR / "lib" / "usr" / "lib" / "x86_64-linux-gnu"
LIB_FILE = LIB_PATH / "libxcb-cursor.so.0"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Pre-load bundled libxcb-cursor if present to allow headless/X11 PyQt6 initialization
if LIB_FILE.exists():
    try:
        import ctypes
        ctypes.cdll.LoadLibrary(str(LIB_FILE))
    except Exception:
        pass


class Config:
    """Application configuration holder for the Screentime Clock.

    Attributes:
        app_name: Title of the desktop widget application.
        idle_threshold_seconds: Seconds of user inactivity before marking idle.
        poll_interval_ms: Interval between idle detection and time accumulation ticks.
        ui_refresh_ms: Interval for clock hand and digital display repaints.
    """

    def __init__(self) -> None:
        """Initialize configuration with default operational parameters."""
        self.app_name: str = "24H Screentime Clock"
        self.idle_threshold_seconds: int = 180  # 3 minutes of mouse/kb inactivity
        self.poll_interval_ms: int = 1000       # 1 second tracking tick
        self.ui_refresh_ms: int = 100           # Smooth 10 FPS clock updates


config = Config()
