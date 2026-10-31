"""Desktop Widget for 24-Hour Screentime and Session Monitoring.

Provides a draggable, frameless glassmorphic HUD displaying real-time
screentime metrics, analog 24-hour dial, and historical session diagnostics.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import CONFIG_FILE, config
from gui.clock_dial import Analog24HourClockDial
from gui.styles import (
    ACCENT_AMBER,
    ACCENT_CYAN,
    ACCENT_EMERALD,
    ACCENT_ROSE,
    BORDER_GLASS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WIDGET_STYLE,
)
from tracker import ScreentimeTracker, format_duration


class ScreentimeDesktopWidget(QWidget):
    """Floating desktop widget displaying 24h analog clock and screentime metrics.

    Attributes:
        tracker: ScreentimeTracker instance maintaining session history.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize desktop widget window flags, layout, and update timers."""
        super().__init__(parent)
        self.tracker = ScreentimeTracker()
        self._drag_pos: QPoint | None = None
        self._is_expanded: bool = False
        self._always_on_top: bool = False

        # Frameless, translucent glass window configuration
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(WIDGET_STYLE)

        self._build_ui()
        self._load_geometry()

        # High-frequency timer for smooth clock hand animation & digital tick
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(config.ui_refresh_ms)
        self.clock_timer.timeout.connect(self._update_display)
        self.clock_timer.start()

        # Background screentime tracker accumulation tick (every 1s)
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(config.poll_interval_ms)
        self.track_timer.timeout.connect(self.tracker.tick)
        self.track_timer.start()

        self._update_display()

    def _build_ui(self) -> None:
        """Construct the widget layouts, clock dial, and HUD badges."""
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(10, 10, 10, 10)

        # Central glass container
        self.container = QWidget(self)
        self.container.setObjectName("CentralWidget")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 14, 16, 16)
        self.container_layout.setSpacing(10)

        # ─── 1. Header Bar ──────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        self.pulse_dot = QLabel("●")
        self.pulse_dot.setStyleSheet(f"color: {ACCENT_EMERALD}; font-size: 11px;")
        header.addWidget(self.pulse_dot)

        self.title_label = QLabel("CHRONOS 24H")
        self.title_label.setObjectName("TitleLabel")
        header.addWidget(self.title_label)

        header.addStretch()

        # Expand/Collapse toggle button
        self.btn_toggle_expand = QPushButton("▾")
        self.btn_toggle_expand.setObjectName("IconButton")
        self.btn_toggle_expand.setToolTip("Toggle Detailed Session Diagnostics")
        self.btn_toggle_expand.clicked.connect(self._toggle_expand)
        header.addWidget(self.btn_toggle_expand)

        # Pin-to-top button
        self.btn_pin = QPushButton("📌")
        self.btn_pin.setObjectName("IconButton")
        self.btn_pin.setToolTip("Toggle Always on Top")
        self.btn_pin.clicked.connect(self._toggle_always_on_top)
        header.addWidget(self.btn_pin)

        # Close button
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("IconButton")
        self.btn_close.setToolTip("Close Screentime Clock")
        self.btn_close.clicked.connect(self.close)
        header.addWidget(self.btn_close)

        self.container_layout.addLayout(header)

        # ─── 2. 24-Hour Analog Clock Dial ───────────────────────────────────
        dial_container = QHBoxLayout()
        dial_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_dial = Analog24HourClockDial(self)
        dial_container.addWidget(self.clock_dial)
        self.container_layout.addLayout(dial_container)

        # ─── 3. Dual Screentime Metric Badges (Today vs Last Session) ────────
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(10)

        # Pill 1: Today's Screentime
        self.pill_today = QFrame()
        self.pill_today.setObjectName("PillToday")
        p_today_layout = QVBoxLayout(self.pill_today)
        p_today_layout.setContentsMargins(10, 8, 10, 8)
        p_today_layout.setSpacing(2)

        lbl_today_title = QLabel("TODAY'S SCREENTIME")
        lbl_today_title.setObjectName("PillTodayTitle")
        self.lbl_today_val = QLabel("00h 00m 00s")
        self.lbl_today_val.setObjectName("PillTodayVal")
        self.lbl_today_sub = QLabel("0.0% of day")
        self.lbl_today_sub.setStyleSheet(f"font-size: 10px; color: {TEXT_SECONDARY};")

        p_today_layout.addWidget(lbl_today_title)
        p_today_layout.addWidget(self.lbl_today_val)
        p_today_layout.addWidget(self.lbl_today_sub)
        pills_layout.addWidget(self.pill_today)

        # Pill 2: Last Login Session
        self.pill_last = QFrame()
        self.pill_last.setObjectName("PillLast")
        p_last_layout = QVBoxLayout(self.pill_last)
        p_last_layout.setContentsMargins(10, 8, 10, 8)
        p_last_layout.setSpacing(2)

        lbl_last_title = QLabel("LAST LOGIN SESSION")
        lbl_last_title.setObjectName("PillLastTitle")
        self.lbl_last_val = QLabel("00h 00m")
        self.lbl_last_val.setObjectName("PillLastVal")
        self.lbl_last_sub = QLabel("Prior session")
        self.lbl_last_sub.setStyleSheet(f"font-size: 10px; color: {TEXT_SECONDARY};")

        p_last_layout.addWidget(lbl_last_title)
        p_last_layout.addWidget(self.lbl_last_val)
        p_last_layout.addWidget(self.lbl_last_sub)
        pills_layout.addWidget(self.pill_last)

        self.container_layout.addLayout(pills_layout)

        # ─── 4. Expandable Detailed Diagnostics Drawer ───────────────────────
        self.expandable_section = QWidget()
        self.expand_layout = QVBoxLayout(self.expandable_section)
        self.expand_layout.setContentsMargins(0, 6, 0, 0)
        self.expand_layout.setSpacing(8)

        # Divider line
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {BORDER_GLASS};")
        self.expand_layout.addWidget(divider)

        # Diagnostics heading
        head_diag = QLabel("SESSION BREAKDOWN & DIAGNOSTICS")
        head_diag.setObjectName("DetailHeader")
        self.expand_layout.addWidget(head_diag)

        # Detail rows
        self.lbl_det_active = QLabel("Active Time: 00h 00m")
        self.lbl_det_active.setStyleSheet(f"font-size: 11px; color: {TEXT_PRIMARY};")
        self.expand_layout.addWidget(self.lbl_det_active)

        self.lbl_det_cur_start = QLabel("Current Session: --")
        self.lbl_det_cur_start.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        self.expand_layout.addWidget(self.lbl_det_cur_start)

        self.lbl_det_last_info = QLabel("Last Session: --")
        self.lbl_det_last_info.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        self.lbl_det_last_info.setWordWrap(True)
        self.expand_layout.addWidget(self.lbl_det_last_info)

        # Controls in drawer
        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        self.btn_toggle_dial_mode = QPushButton("Arc Mode: Timeline")
        self.btn_toggle_dial_mode.clicked.connect(self._toggle_dial_mode)
        btns_row.addWidget(self.btn_toggle_dial_mode)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self._on_refresh_requested)
        btns_row.addWidget(self.btn_refresh)

        self.expand_layout.addLayout(btns_row)

        self.expandable_section.setVisible(False)
        self.container_layout.addWidget(self.expandable_section)

        self.root_layout.addWidget(self.container)

    def _update_display(self) -> None:
        """Update live screentime metrics, analog dial, and HUD badges."""
        today_total_sec = self.tracker.get_today_total_seconds()
        today_active_sec = self.tracker.get_today_active_seconds()
        last_sec = self.tracker.get_last_session_seconds()
        today_intervals = self.tracker.get_today_intervals()
        last_interval = self.tracker.get_last_session_interval()

        idle_sec = self.tracker.idle_detector.get_idle_seconds()
        is_active = idle_sec < config.idle_threshold_seconds

        # Update pulse dot color
        self.pulse_dot.setStyleSheet(
            f"color: {ACCENT_EMERALD if is_active else ACCENT_AMBER}; font-size: 11px;"
        )

        # Update clock dial vector graphics
        self.clock_dial.set_metrics(
            today_sec=today_total_sec,
            last_sec=last_sec,
            today_intervals=today_intervals,
            last_interval=last_interval,
            is_active=is_active,
        )

        # Update Today's Screentime Pill
        self.lbl_today_val.setText(format_duration(today_total_sec, show_seconds=True))
        day_pct = (today_total_sec / 86400.0) * 100.0
        self.lbl_today_sub.setText(f"{day_pct:.1f}% of 24h")

        # Update Last Session Pill
        self.lbl_last_val.setText(format_duration(last_sec, show_seconds=False))
        if self.tracker.last_session:
            s_date = self.tracker.last_session.start.strftime("%a %b %d")
            self.lbl_last_sub.setText(f"{s_date}")
        else:
            self.lbl_last_sub.setText("No prior session")

        # Update expanded drawer metrics
        if self._is_expanded:
            self.lbl_det_active.setText(
                f"Active: {format_duration(today_active_sec, False)} | Idle: {format_duration(max(0, today_total_sec - today_active_sec), False)}"
            )
            if self.tracker.current_session:
                c_start = self.tracker.current_session.start.strftime("%a %b %d %H:%M")
                self.lbl_det_cur_start.setText(f"Current Session Started: {c_start}")
            if self.tracker.last_session:
                ls = self.tracker.last_session
                end_str = ls.end.strftime("%H:%M") if ls.end else "Unknown"
                self.lbl_det_last_info.setText(
                    f"Last: {ls.start.strftime('%a %b %d %H:%M')} - {end_str} ({format_duration(last_sec, False)})"
                )

    def _toggle_expand(self) -> None:
        """Toggle detailed session diagnostics drawer visibility."""
        self._is_expanded = not self._is_expanded
        self.expandable_section.setVisible(self._is_expanded)
        self.btn_toggle_expand.setText("▴" if self._is_expanded else "▾")
        self.adjustSize()
        self._save_geometry()

    def _toggle_always_on_top(self) -> None:
        """Toggle always-on-top window layering."""
        self._always_on_top = not self._always_on_top
        flags = self.windowFlags()
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            self.btn_pin.setStyleSheet(f"color: {ACCENT_CYAN};")
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
            self.btn_pin.setStyleSheet(f"color: {TEXT_MUTED};")
        self.setWindowFlags(flags)
        self.show()

    def _toggle_dial_mode(self) -> None:
        """Toggle clock dial between timeline intervals and cumulative gauge."""
        self.clock_dial.toggle_mode()
        mode_name = "Timeline" if self.clock_dial.show_timeline_mode else "Gauge"
        self.btn_toggle_dial_mode.setText(f"Arc Mode: {mode_name}")

    def _on_refresh_requested(self) -> None:
        """Reload system session records and refresh display."""
        self.tracker._refresh_system_sessions()
        self._update_display()

    # ─── Mouse Dragging & Screen Geometry Persistence ───────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Record drag start point on mouse press.

        Args:
            event: Mouse press event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move widget according to cursor drag.

        Args:
            event: Mouse move event.
        """
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Save new widget position on release.

        Args:
            event: Mouse release event.
        """
        self._drag_pos = None
        self._save_geometry()
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Display right-click context menu.

        Args:
            event: Context menu event.
        """
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: #121826; color: #FFFFFF; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; padding: 6px; }} "
            f"QMenu::item:selected {{ background-color: {ACCENT_CYAN}; color: #000000; border-radius: 4px; }}"
        )

        action_expand = menu.addAction("Collapse Diagnostics" if self._is_expanded else "Expand Diagnostics")
        action_expand.triggered.connect(self._toggle_expand)

        action_mode = menu.addAction(
            "Switch to Cumulative Gauge Arc" if self.clock_dial.show_timeline_mode else "Switch to Timeline Interval Arc"
        )
        action_mode.triggered.connect(self._toggle_dial_mode)

        action_refresh = menu.addAction("🔄 Refresh Session History")
        action_refresh.triggered.connect(self._on_refresh_requested)

        menu.addSeparator()

        action_ontop = menu.addAction("Unpin from Top" if self._always_on_top else "Pin to Top")
        action_ontop.triggered.connect(self._toggle_always_on_top)

        menu.addSeparator()

        action_close = menu.addAction("✕ Close Widget")
        action_close.triggered.connect(self.close)

        menu.exec(event.globalPos())

    def _save_geometry(self) -> None:
        """Persist widget screen coordinates and expanded state to JSON."""
        data = {
            "x": self.x(),
            "y": self.y(),
            "is_expanded": self._is_expanded,
            "always_on_top": self._always_on_top,
            "timeline_mode": self.clock_dial.show_timeline_mode,
        }
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_geometry(self) -> None:
        """Restore saved widget position from JSON."""
        if not CONFIG_FILE.exists():
            # Default to top-left or right side of screen
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                self.move(60, 60)
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            x = data.get("x", 60)
            y = data.get("y", 60)
            self.move(x, y)
            if data.get("is_expanded", False):
                self._toggle_expand()
            if not data.get("timeline_mode", True):
                self.clock_dial.show_timeline_mode = False
        except Exception:
            pass
