"""Analog 24-Hour Clock Dial for Screentime Visualization.

Renders an antialiased 24-hour dial with concentric glowing arcs displaying
today's active screentime intervals and the previous login session duration.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QWidget

from gui.styles import (
    ACCENT_AMBER,
    ACCENT_CYAN,
    ACCENT_EMERALD,
    ACCENT_PURPLE,
    ACCENT_ROSE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from tracker import format_duration


class Analog24HourClockDial(QWidget):
    """Custom-rendered vector 24-hour analog clock with dual screentime arcs.

    Attributes:
        today_seconds: Total active/session screentime today in seconds.
        last_session_seconds: Duration of previous login session in seconds.
        today_intervals: List of (start_hour, end_hour) tuples active today.
        last_session_interval: (start_hour, end_hour) tuple of last session.
        is_active: True if user is actively using the system (not idle).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize 24-hour analog clock widget."""
        super().__init__(parent)
        self.today_seconds: float = 0.0
        self.last_session_seconds: float = 0.0
        self.today_intervals: list[tuple[float, float]] = []
        self.last_session_interval: tuple[float, float] | None = None
        self.is_active: bool = True
        self.show_timeline_mode: bool = True

        self.setMinimumSize(220, 220)

    def set_metrics(
        self,
        today_sec: float,
        last_sec: float,
        today_intervals: list[tuple[float, float]],
        last_interval: tuple[float, float] | None,
        is_active: bool,
    ) -> None:
        """Update dial screentime metrics and schedule visual repaint.

        Args:
            today_sec: Today's screentime in seconds.
            last_sec: Last session screentime in seconds.
            today_intervals: Active (start_hr, end_hr) floating hour intervals.
            last_interval: Previous session's (start_hr, end_hr) interval.
            is_active: True if active input detected within idle threshold.
        """
        self.today_seconds = today_sec
        self.last_session_seconds = last_sec
        self.today_intervals = today_intervals
        self.last_session_interval = last_interval
        self.is_active = is_active
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render the 24-hour dial, screentime arcs, hour numerals, and analog hands.

        Args:
            event: Paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h)
        center_x = w / 2.0
        center_y = h / 2.0
        radius = (size / 2.0) - 8.0

        if radius <= 30:
            painter.end()
            return

        # ─── 1. Background Dial Plate with Day/Night Hemisphere ─────────────
        dial_rect = QRectF(center_x - radius, center_y - radius, radius * 2.0, radius * 2.0)
        
        # Dial gradient with subtle Day/Night shading
        bg_gradient = QConicalGradient(QPointF(center_x, center_y), -90.0)
        # Night at top (18h to 06h)
        bg_gradient.setColorAt(0.0, QColor(10, 14, 24, 240))
        bg_gradient.setColorAt(0.25, QColor(16, 24, 40, 240))  # 06:00 Dawn
        bg_gradient.setColorAt(0.50, QColor(22, 32, 52, 240))  # 12:00 Noon
        bg_gradient.setColorAt(0.75, QColor(16, 24, 40, 240))  # 18:00 Dusk
        bg_gradient.setColorAt(1.0, QColor(10, 14, 24, 240))   # 24:00 Midnight

        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.5))
        painter.setBrush(QBrush(bg_gradient))
        painter.drawEllipse(dial_rect)

        # ─── 2. Screentime Arcs ──────────────────────────────────────────────
        # Track 1: Outer Arc (Radius * 0.88) -> Today's Screentime
        r_today = radius * 0.88
        rect_today = QRectF(center_x - r_today, center_y - r_today, r_today * 2.0, r_today * 2.0)

        # Background track for Today's arc
        pen_track_today = QPen(QColor(255, 255, 255, 14), 7.0)
        pen_track_today.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_track_today)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect_today)

        # Today's active intervals arc
        if self.show_timeline_mode and self.today_intervals:
            pen_today_active = QPen(QColor(ACCENT_CYAN), 7.0)
            pen_today_active.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_today_active)

            for start_h, end_h in self.today_intervals:
                span_h = max(0.05, end_h - start_h)
                # Clockwise from top (00:00)
                # Qt start angle in 1/16th deg: (90 - start_h * 15) * 16
                qt_start = int((90.0 - (start_h * 15.0)) * 16.0)
                qt_span = int(-(span_h * 15.0) * 16.0)
                painter.drawArc(rect_today, qt_start, qt_span)
        else:
            # Cumulative Gauge Mode
            hours_today = self.today_seconds / 3600.0
            span_deg = min(360.0, (hours_today / 24.0) * 360.0)
            if span_deg > 0.5:
                pen_today_gauge = QPen(QColor(ACCENT_CYAN), 7.0)
                pen_today_gauge.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen_today_gauge)
                qt_start = 90 * 16
                qt_span = int(-span_deg * 16.0)
                painter.drawArc(rect_today, qt_start, qt_span)

        # Track 2: Concentric Inner Arc (Radius * 0.74) -> Last Login Session
        r_last = radius * 0.74
        rect_last = QRectF(center_x - r_last, center_y - r_last, r_last * 2.0, r_last * 2.0)

        # Background track for Last Session arc
        pen_track_last = QPen(QColor(255, 255, 255, 10), 5.0)
        pen_track_last.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_track_last)
        painter.drawEllipse(rect_last)

        # Last session interval arc
        if self.last_session_interval:
            s_start, s_end = self.last_session_interval
            span_h = max(0.08, s_end - s_start)
            pen_last = QPen(QColor(ACCENT_ROSE), 5.0)
            pen_last.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_last)
            qt_start = int((90.0 - (s_start * 15.0)) * 16.0)
            qt_span = int(-(span_h * 15.0) * 16.0)
            painter.drawArc(rect_last, qt_start, qt_span)
        elif self.last_session_seconds > 0:
            # Render duration gauge arc
            last_h = self.last_session_seconds / 3600.0
            span_deg = min(360.0, (last_h / 24.0) * 360.0)
            pen_last = QPen(QColor(ACCENT_ROSE), 5.0)
            pen_last.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_last)
            qt_start = 90 * 16
            qt_span = int(-span_deg * 16.0)
            painter.drawArc(rect_last, qt_start, qt_span)

        # ─── 3. Dial Hour Ticks and 24-Hour Numerals ────────────────────────
        r_ticks = radius * 0.96
        for h_idx in range(24):
            angle_deg = h_idx * 15.0
            angle_rad = math.radians(angle_deg - 90.0)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)

            # Major vs minor tick
            is_cardinal = h_idx % 6 == 0  # 00, 06, 12, 18
            is_major = h_idx % 2 == 0     # Even hours

            tick_len = 8.0 if is_cardinal else (5.5 if is_major else 3.5)
            tick_color = (
                QColor(ACCENT_CYAN)
                if is_cardinal
                else (QColor(255, 255, 255, 140) if is_major else QColor(255, 255, 255, 60))
            )
            pen_tick = QPen(tick_color, 1.8 if is_cardinal else (1.2 if is_major else 0.8))
            painter.setPen(pen_tick)

            p1 = QPointF(center_x + (r_ticks * cos_a), center_y + (r_ticks * sin_a))
            p2 = QPointF(center_x + ((r_ticks - tick_len) * cos_a), center_y + ((r_ticks - tick_len) * sin_a))
            painter.drawLine(p1, p2)

            # Numerals for even hours (00, 02, 04, 06, 08, 10, 12, 14, 16, 18, 20, 22)
            if is_major:
                r_num = radius * 0.60
                nx = center_x + (r_num * cos_a)
                ny = center_y + (r_num * sin_a)

                num_font_size = max(6, int(radius * 0.08))
                painter.setFont(QFont("Segoe UI", num_font_size, QFont.Weight.Bold if is_cardinal else QFont.Weight.Normal))
                painter.setPen(QColor(TEXT_PRIMARY if is_cardinal else TEXT_MUTED))

                num_rect = QRectF(nx - 14, ny - 10, 28, 20)
                painter.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, f"{h_idx:02d}")

        # ─── 4. Precision Analog Clock Hands ────────────────────────────────
        now = datetime.now()
        cur_h = now.hour + (now.minute / 60.0) + (now.second / 3600.0)
        cur_m = now.minute + (now.second / 60.0)

        # 24-Hour Hour Hand (points to current time of day)
        hour_angle_deg = cur_h * 15.0
        hour_angle_rad = math.radians(hour_angle_deg - 90.0)
        h_cos = math.cos(hour_angle_rad)
        h_sin = math.sin(hour_angle_rad)
        r_hour_hand = radius * 0.50

        # Draw glowing hour needle
        pen_hour = QPen(QColor(ACCENT_CYAN), 2.5)
        pen_hour.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_hour)
        painter.drawLine(
            QPointF(center_x - (10.0 * h_cos), center_y - (10.0 * h_sin)),
            QPointF(center_x + (r_hour_hand * h_cos), center_y + (r_hour_hand * h_sin)),
        )

        # Luminous arrow tip for hour hand
        tip_pt = QPointF(center_x + (r_hour_hand * h_cos), center_y + (r_hour_hand * h_sin))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(ACCENT_CYAN)))
        painter.drawEllipse(tip_pt, 3.5, 3.5)

        # Minute Hand (60 minutes per full 360 rotation)
        min_angle_deg = cur_m * 6.0
        min_angle_rad = math.radians(min_angle_deg - 90.0)
        m_cos = math.cos(min_angle_rad)
        m_sin = math.sin(min_angle_rad)
        r_min_hand = radius * 0.68

        pen_min = QPen(QColor(255, 255, 255, 210), 1.6)
        pen_min.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_min)
        painter.drawLine(
            QPointF(center_x - (12.0 * m_cos), center_y - (12.0 * m_sin)),
            QPointF(center_x + (r_min_hand * m_cos), center_y + (r_min_hand * m_sin)),
        )

        # ─── 5. Center Hub and Digital Readout ───────────────────────────────
        # Central pivot jewel
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        painter.setBrush(QBrush(QColor(12, 16, 26)))
        painter.drawEllipse(QPointF(center_x, center_y), 7.0, 7.0)

        # Activity dot inside center jewel
        status_color = QColor(ACCENT_EMERALD if self.is_active else ACCENT_AMBER)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(status_color))
        painter.drawEllipse(QPointF(center_x, center_y), 3.0, 3.0)

        # Digital time stamp directly under center hub
        time_str = now.strftime("%H:%M:%S")
        painter.setFont(QFont("Courier New", max(7, int(radius * 0.09)), QFont.Weight.Bold))
        painter.setPen(QColor(ACCENT_CYAN))
        clock_rect = QRectF(center_x - 45, center_y + 12, 90, 18)
        painter.drawText(clock_rect, Qt.AlignmentFlag.AlignCenter, time_str)

        # Mode indicator caption
        mode_str = "24H TIMELINE" if self.show_timeline_mode else "24H GAUGE"
        painter.setFont(QFont("Segoe UI", max(5, int(radius * 0.05)), QFont.Weight.DemiBold))
        painter.setPen(QColor(TEXT_MUTED))
        mode_rect = QRectF(center_x - 45, center_y + 26, 90, 12)
        painter.drawText(mode_rect, Qt.AlignmentFlag.AlignCenter, mode_str)

        painter.end()

    def toggle_mode(self) -> None:
        """Toggle between 24h timeline interval arcs and cumulative gauge arcs."""
        self.show_timeline_mode = not self.show_timeline_mode
        self.update()
