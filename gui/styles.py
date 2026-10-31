"""Design system, color tokens, and stylesheets for 24-Hour Analog Screentime Clock.

Features dark obsidian glassmorphism, neon cyan and rose accents, and high-legibility typography.
"""

from __future__ import annotations

# Color Palette Tokens
BG_DARK = "#090d16"
BG_GLASS = "rgba(14, 18, 28, 0.92)"
BG_GLASS_LIGHT = "rgba(24, 32, 48, 0.70)"
BORDER_GLASS = "rgba(255, 255, 255, 0.12)"
BORDER_GLOW = "rgba(0, 240, 255, 0.40)"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"

# Screentime Visual Theme Accents
ACCENT_CYAN = "#00F0FF"    # Today's Screentime & Active Clock Hands
ACCENT_ROSE = "#FF2E63"    # Last Session Screentime & Alert Bounds
ACCENT_EMERALD = "#00E676" # Active Screen State & Healthy Work Intervals
ACCENT_AMBER = "#FFB300"   # Session Benchmarks & Warning States
ACCENT_PURPLE = "#A855F7"  # Deep Historical Metrics & Night Atmosphere

# Main Widget QSS Stylesheet
WIDGET_STYLE = f"""
QWidget#CentralWidget {{
    background-color: {BG_GLASS};
    border: 1px solid {BORDER_GLASS};
    border-radius: 20px;
}}

QLabel {{
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'Ubuntu', 'DejaVu Sans', sans-serif;
}}

QLabel#TitleLabel {{
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1.5px;
    color: {TEXT_PRIMARY};
}}

QLabel#DigitalClock {{
    font-family: 'Courier New', 'DejaVu Sans Mono', monospace;
    font-size: 15px;
    font-weight: 700;
    color: {ACCENT_CYAN};
    letter-spacing: 1px;
}}

QLabel#PillTodayTitle {{
    font-size: 9px;
    font-weight: 800;
    color: {ACCENT_CYAN};
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

QLabel#PillTodayVal {{
    font-family: 'Courier New', 'DejaVu Sans Mono', monospace;
    font-size: 14px;
    font-weight: 800;
    color: #FFFFFF;
}}

QLabel#PillLastTitle {{
    font-size: 9px;
    font-weight: 800;
    color: {ACCENT_ROSE};
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

QLabel#PillLastVal {{
    font-family: 'Courier New', 'DejaVu Sans Mono', monospace;
    font-size: 14px;
    font-weight: 800;
    color: #FFFFFF;
}}

QLabel#DetailHeader {{
    font-size: 10px;
    font-weight: 800;
    color: {ACCENT_CYAN};
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QLabel#DetailRowTitle {{
    font-size: 11px;
    color: {TEXT_SECONDARY};
}}

QLabel#DetailRowVal {{
    font-size: 11px;
    font-weight: 700;
    color: #FFFFFF;
}}

QFrame#PillToday {{
    background-color: rgba(0, 240, 255, 0.08);
    border: 1px solid rgba(0, 240, 255, 0.25);
    border-radius: 10px;
}}

QFrame#PillLast {{
    background-color: rgba(255, 46, 99, 0.08);
    border: 1px solid rgba(255, 46, 99, 0.25);
    border-radius: 10px;
}}

QPushButton {{
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 7px;
    color: {TEXT_PRIMARY};
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: rgba(0, 240, 255, 0.15);
    border: 1px solid {ACCENT_CYAN};
    color: #FFFFFF;
}}

QPushButton:pressed {{
    background-color: rgba(0, 240, 255, 0.25);
}}

QPushButton#IconButton {{
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    font-size: 13px;
    padding: 2px 5px;
}}

QPushButton#IconButton:hover {{
    color: {TEXT_PRIMARY};
    background-color: rgba(255, 255, 255, 0.10);
    border-radius: 6px;
}}

QProgressBar {{
    background-color: rgba(255, 255, 255, 0.06);
    border: none;
    border-radius: 3px;
    height: 5px;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_EMERALD});
    border-radius: 3px;
}}
"""
