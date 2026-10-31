"""Screentime and session analysis engine.

Tracks active vs. idle screen time via X11 XScreenSaver extensions, parses system wtmp
records via `last` and `loginctl`, and computes today's and previous session metrics.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from config import CONFIG_FILE, HISTORY_FILE, config


class XScreenSaverInfo(ctypes.Structure):
    """C structure matching XScreenSaverInfo for querying X11 idle milliseconds."""

    _fields_ = [
        ("window", ctypes.c_ulong),
        ("state", ctypes.c_int),
        ("kind", ctypes.c_int),
        ("til_or_since", ctypes.c_ulong),
        ("idle", ctypes.c_ulong),
    ]


class X11IdleDetector:
    """Interacts with libX11 and libXss to detect user mouse and keyboard idle duration."""

    def __init__(self) -> None:
        """Initialize X11 library pointers and XScreenSaver query functions."""
        self._available: bool = False
        self._x11: ctypes.CDLL | None = None
        self._xss: ctypes.CDLL | None = None
        self._display: ctypes.c_void_p | None = None
        self._root_window: ctypes.c_ulong = 0

        try:
            self._x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
            xss_name = ctypes.util.find_library("Xss") or "libXss.so.1"
            self._xss = ctypes.cdll.LoadLibrary(xss_name)

            self._x11.XOpenDisplay.restype = ctypes.c_void_p
            self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
            self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]

            self._xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
            self._xss.XScreenSaverQueryInfo.restype = ctypes.c_int
            self._xss.XScreenSaverQueryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(XScreenSaverInfo),
            ]
            self._x11.XFree.argtypes = [ctypes.c_void_p]
            self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

            # Test connection
            disp = self._x11.XOpenDisplay(None)
            if disp:
                self._available = True
                self._x11.XCloseDisplay(disp)
        except Exception:
            self._available = False

    def get_idle_seconds(self) -> float:
        """Retrieve the number of seconds since last user input.

        Returns:
            float: Inactivity duration in seconds, or 0.0 on query failure.
        """
        if not self._available or not self._x11 or not self._xss:
            return 0.0

        try:
            disp = self._x11.XOpenDisplay(None)
            if not disp:
                return 0.0
            root = self._x11.XDefaultRootWindow(disp)
            info = self._xss.XScreenSaverAllocInfo()
            self._xss.XScreenSaverQueryInfo(disp, root, info)
            idle_ms = info.contents.idle
            self._x11.XFree(info)
            self._x11.XCloseDisplay(disp)
            return float(idle_ms) / 1000.0
        except Exception:
            return 0.0


@dataclass
class SessionRecord:
    """Historical representation of a user login session.

    Attributes:
        start: Datetime when the session began.
        end: Datetime when the session terminated, or None if currently active.
        duration_seconds: Total duration of the session in seconds.
        tty_or_display: Terminal or display identifier (e.g., ':0' or 'tty7').
        is_current: True if this record represents the active ongoing session.
    """

    start: datetime
    end: datetime | None
    duration_seconds: float
    tty_or_display: str
    is_current: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert session record to dictionary for JSON persistence.

        Returns:
            dict[str, Any]: Serialized record dictionary.
        """
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "duration_seconds": self.duration_seconds,
            "tty_or_display": self.tty_or_display,
            "is_current": self.is_current,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        """Reconstruct session record from dictionary.

        Args:
            data: Serialized record dictionary.

        Returns:
            SessionRecord: Hydrated record.
        """
        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]) if data.get("end") else None,
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            tty_or_display=data.get("tty_or_display", ":0"),
            is_current=data.get("is_current", False),
        )


class ScreentimeTracker:
    """Manages screentime accumulation, historical login analysis, and timeline segments.

    Attributes:
        current_session: Record for the active session.
        last_session: Record for the most recently completed session prior to current.
        today_completed_sessions: List of completed sessions that took place today.
    """

    def __init__(self) -> None:
        """Initialize screentime tracker and inspect system session records."""
        self.idle_detector: X11IdleDetector = X11IdleDetector()
        self.current_session: SessionRecord | None = None
        self.last_session: SessionRecord | None = None
        self.today_completed_sessions: list[SessionRecord] = []

        # Real-time accumulation for current active app session
        self._active_seconds_today: float = 0.0
        self._total_seconds_today: float = 0.0
        self._last_tick_time: datetime = datetime.now()
        self._current_date_str: str = datetime.now().strftime("%Y-%m-%d")

        # Load persisted history and parse wtmp system records
        self._refresh_system_sessions()
        self._load_persisted_state()

    def _get_journal_sessions(
        self, target_user: str | None = None, max_boots: int = 10
    ) -> tuple[list[SessionRecord], SessionRecord | None]:
        """Extract monotonic-calibrated sessions from systemd journal to prevent RTC skew.

        Hardware RTC clock drift, dual-boot Windows/Linux localtime mismatches, and
        network time steps (NTP) corrupt wall-clock differences recorded in wtmp/last.
        Systemd journal records monotonic timestamps (`__MONOTONIC_TIMESTAMP`) alongside
        realtime timestamps. Monotonic duration is strictly immune to RTC adjustments.
        The accurate wall-clock start time is computed as:
        `wall_start = wall_end - timedelta(seconds=monotonic_duration)`.

        Args:
            target_user: Linux username to inspect. Defaults to current login user.
            max_boots: Maximum number of prior boot cycles to inspect. Defaults to 10.

        Returns:
            tuple[list[SessionRecord], SessionRecord | None]: List of completed session
                records, and an optional current session record if discovered.
        """
        if not target_user:
            target_user = os.getenv("USER", "ameya")

        today_date = datetime.now().date()
        completed_records: list[SessionRecord] = []
        current_record: SessionRecord | None = None

        try:
            boots_raw = subprocess.check_output(
                ["journalctl", "--list-boots"], stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="ignore")
            available_boots: list[int] = []
            for line in boots_raw.splitlines():
                parts = line.strip().split()
                if parts and parts[0].lstrip("-+").isdigit():
                    available_boots.append(int(parts[0]))
        except Exception:
            return completed_records, current_record

        start_pattern = rf"Started\s+(session-[a-zA-Z0-9]+\.scope)\s+-\s+Session\s+[a-zA-Z0-9]+\s+of\s+User\s+{target_user}"
        stop_pattern = rf"Stopped\s+(session-[a-zA-Z0-9]+\.scope)\s+-\s+Session\s+[a-zA-Z0-9]+\s+of\s+User\s+{target_user}"

        active_scopes: set[str] = set()
        try:
            loginctl_out = subprocess.check_output(
                ["loginctl", "list-sessions", "--no-legend"], stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="ignore")
            for line in loginctl_out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[2] == target_user:
                    active_scopes.add(f"session-{parts[0]}.scope")
        except Exception:
            pass

        # Inspect boot 0 first, then -1, -2, etc.
        prior_boots = [b for b in sorted(available_boots, reverse=True) if b < 0][:max_boots]
        boot_list = [0] + prior_boots

        for boot_offset in boot_list:
            cmd = ["journalctl", f"-b{boot_offset}", "-o", "json", "-u", "session-*.scope"]
            try:
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(
                    "utf-8", errors="ignore"
                )
            except Exception:
                continue

            lines = [l for l in out.splitlines() if l.strip()]
            if not lines:
                continue

            scope_events: dict[str, dict[str, Any]] = {}
            for line in lines:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                unit = entry.get("UNIT") or entry.get("_SYSTEMD_UNIT")
                msg = entry.get("MESSAGE", "")
                mono_us = entry.get("__MONOTONIC_TIMESTAMP")
                real_us = entry.get("__REALTIME_TIMESTAMP")

                if not unit or not mono_us:
                    continue

                if unit not in scope_events:
                    if re.search(start_pattern, msg):
                        scope_events[unit] = {
                            "start_mono_us": int(mono_us),
                            "start_real_us": int(real_us) if real_us else None,
                            "end_mono_us": int(mono_us),
                            "end_real_us": int(real_us) if real_us else None,
                            "stopped": False,
                            "boot_offset": boot_offset,
                            "unit": unit,
                        }
                else:
                    scope_events[unit]["end_mono_us"] = int(mono_us)
                    if real_us:
                        scope_events[unit]["end_real_us"] = int(real_us)
                    if re.search(stop_pattern, msg) or "Deactivated successfully" in msg:
                        scope_events[unit]["stopped"] = True

            for unit, data in scope_events.items():
                start_mono = data["start_mono_us"] / 1_000_000.0

                if boot_offset == 0 and unit in active_scopes and not data["stopped"]:
                    cur_mono = time.monotonic()
                    dur = max(0.0, cur_mono - start_mono)
                    now_dt = datetime.now()
                    calc_start = now_dt - timedelta(seconds=dur)
                    current_record = SessionRecord(
                        start=calc_start,
                        end=None,
                        duration_seconds=dur,
                        tty_or_display=":0",
                        is_current=True,
                    )
                    continue

                end_mono = (data["end_mono_us"] or data["start_mono_us"]) / 1_000_000.0
                duration = max(0.0, end_mono - start_mono)
                # Ignore trivial sessions under 60s
                if duration < 60.0:
                    continue

                end_real = (data["end_real_us"] or data["start_real_us"]) / 1_000_000.0
                end_dt = datetime.fromtimestamp(end_real)
                calc_start = end_dt - timedelta(seconds=duration)

                completed_records.append(
                    SessionRecord(
                        start=calc_start,
                        end=end_dt,
                        duration_seconds=duration,
                        tty_or_display=":0",
                        is_current=False,
                    )
                )

            # Once we find completed session(s) in a prior boot that started before today,
            # we have the latest prior login session and can stop searching older boots.
            if completed_records and boot_offset < 0:
                has_prior_day = any(r.start.date() < today_date for r in completed_records)
                if has_prior_day:
                    break

        return completed_records, current_record

    def _parse_wtmp_sessions(self) -> list[SessionRecord]:
        """Parse wtmp records via `last -F -w` as fallback with sanity checks.

        Returns:
            list[SessionRecord]: Parsed session records sorted chronologically.
        """
        try:
            raw_output = subprocess.check_output(
                ["last", "-F", "-w"], stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="ignore")
        except Exception:
            raw_output = ""

        parsed_sessions: list[SessionRecord] = []
        date_pattern = r"([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})"
        regex = re.compile(
            rf"^\s*([a-zA-Z0-9_\-]+)\s+(\S+)\s+(\S+)\s+{date_pattern}\s*(?:-|\s+gone\s+-|\s+still\s+logged\s+in)\s*({date_pattern}|crash|down|still logged in|no logout)?(?:\s+\((?:(\d+)\+)?(\d{2}):(\d{2})\))?"
        )

        current_username = os.getenv("USER", "ameya")

        for line in raw_output.splitlines():
            line = line.strip()
            if not line or not line.startswith(current_username):
                continue

            match = regex.match(line)
            if not match:
                continue

            user = match.group(1)
            tty = match.group(2)
            display = match.group(3)
            start_str = match.group(4)
            end_match = match.group(5)
            days_str = match.group(7)
            hours_str = match.group(8)
            mins_str = match.group(9)

            try:
                start_dt = datetime.strptime(start_str, "%a %b %d %H:%M:%S %Y")
            except Exception:
                continue

            end_dt: datetime | None = None
            if end_match:
                try:
                    end_dt = datetime.strptime(end_match, "%a %b %d %H:%M:%S %Y")
                except Exception:
                    end_dt = None

            duration_sec = 0.0
            if days_str or hours_str or mins_str:
                d = int(days_str) if days_str else 0
                h = int(hours_str) if hours_str else 0
                m = int(mins_str) if mins_str else 0
                duration_sec = float((d * 86400) + (h * 3600) + (m * 60))
            elif end_dt and end_dt >= start_dt:
                duration_sec = (end_dt - start_dt).total_seconds()

            # Guard against negative durations or corrupted records
            duration_sec = max(0.0, duration_sec)
            is_current = end_dt is None and ("still logged in" in line or "gone - no logout" in line)

            parsed_sessions.append(
                SessionRecord(
                    start=start_dt,
                    end=end_dt,
                    duration_seconds=duration_sec,
                    tty_or_display=display or tty,
                    is_current=is_current,
                )
            )

        return parsed_sessions

    def _refresh_system_sessions(self) -> None:
        """Refresh system login sessions using monotonic journal telemetry and wtmp fallback."""
        now = datetime.now()
        today_date = now.date()

        # 1. Primary: Query monotonic journal sessions (immune to RTC offsets & clock jumps)
        journal_completed, journal_current = self._get_journal_sessions()

        if journal_current:
            self.current_session = journal_current

        if journal_completed:
            journal_completed.sort(key=lambda s: s.start, reverse=True)
            self.last_session = journal_completed[0]
            self.today_completed_sessions = [
                s for s in journal_completed if s.start.date() == today_date and s.duration_seconds > 0
            ]

        # 2. If journal didn't provide current or last session, supplement from wtmp records
        if not self.current_session or not self.last_session:
            wtmp_sessions = self._parse_wtmp_sessions()
            if wtmp_sessions:
                wtmp_sessions.sort(key=lambda s: s.start, reverse=True)

                if not self.current_session:
                    first = wtmp_sessions[0]
                    if first.is_current or (now - first.start).total_seconds() < 86400:
                        first.is_current = True
                        self.current_session = first
                        remaining = wtmp_sessions[1:]
                    else:
                        self.current_session = SessionRecord(
                            start=now - timedelta(minutes=10),
                            end=None,
                            duration_seconds=600.0,
                            tty_or_display=":0",
                            is_current=True,
                        )
                        remaining = wtmp_sessions
                else:
                    remaining = wtmp_sessions

                if not self.last_session:
                    for s in remaining:
                        if not s.is_current and s.duration_seconds > 60:
                            self.last_session = s
                            break
                    if not self.last_session and remaining:
                        self.last_session = remaining[0]

                if not self.today_completed_sessions:
                    self.today_completed_sessions = [
                        s for s in remaining if s.start.date() == today_date and s.duration_seconds > 0
                    ]

        # 3. Final fallback if system has zero records
        if not self.current_session:
            boot_time = datetime.now() - timedelta(minutes=15)
            self.current_session = SessionRecord(
                start=boot_time,
                end=None,
                duration_seconds=0.0,
                tty_or_display=":0",
                is_current=True,
            )
        if not self.last_session:
            boot_time = datetime.now() - timedelta(minutes=15)
            self.last_session = SessionRecord(
                start=boot_time - timedelta(hours=6),
                end=boot_time - timedelta(hours=2),
                duration_seconds=14400.0,
                tty_or_display=":0",
                is_current=False,
            )

    def _load_persisted_state(self) -> None:
        """Load persistent history from JSON file."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        loaded = False
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                daily = data.get("daily", {})
                if today_str in daily:
                    today_info = daily[today_str]
                    self._active_seconds_today = float(today_info.get("active_seconds", 0.0))
                    self._total_seconds_today = float(today_info.get("total_seconds", 0.0))
                    loaded = True
            except Exception:
                pass

        if not loaded or self._active_seconds_today <= 0.0:
            total_today = self.get_today_total_seconds()
            idle_now = self.idle_detector.get_idle_seconds()
            self._active_seconds_today = max(0.0, total_today - idle_now)
            self._total_seconds_today = total_today

    def save_state(self) -> None:
        """Persist current day screentime metrics to JSON file."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        data: dict[str, Any] = {"daily": {}, "last_updated": datetime.now().isoformat()}

        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"daily": {}, "last_updated": datetime.now().isoformat()}

        if "daily" not in data:
            data["daily"] = {}

        data["daily"][today_str] = {
            "active_seconds": self.get_today_active_seconds(),
            "total_seconds": self.get_today_total_seconds(),
            "last_session_seconds": self.get_last_session_seconds(),
            "last_session_summary": (
                f"{self.last_session.start.strftime('%a %b %d %H:%M')} - "
                f"{self.last_session.end.strftime('%H:%M') if self.last_session.end else ''}"
                if self.last_session
                else "None"
            ),
        }

        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def tick(self) -> None:
        """Accumulate live active and total screentime based on idle detection."""
        now = datetime.now()
        dt = (now - self._last_tick_time).total_seconds()
        self._last_tick_time = now

        # Handle midnight rollover
        today_str = now.strftime("%Y-%m-%d")
        if today_str != self._current_date_str:
            self._current_date_str = today_str
            self._active_seconds_today = 0.0
            self._total_seconds_today = 0.0

        if dt <= 0 or dt > 60:
            return

        self._total_seconds_today += dt

        idle_sec = self.idle_detector.get_idle_seconds()
        if idle_sec < config.idle_threshold_seconds:
            self._active_seconds_today += dt

        # Periodically persist
        if int(self._total_seconds_today) % 30 == 0:
            self.save_state()

    def get_today_total_seconds(self) -> float:
        """Calculate total login screentime for today.

        Returns:
            float: Total seconds today including current session and prior sessions today.
        """
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)

        # Elapsed in current session today
        current_today_sec = 0.0
        if self.current_session:
            sess_start_today = max(today_start, self.current_session.start)
            current_today_sec = max(0.0, (now - sess_start_today).total_seconds())

        # Prior completed sessions today
        prior_today_sec = sum(s.duration_seconds for s in self.today_completed_sessions)
        return max(self._total_seconds_today, prior_today_sec + current_today_sec)

    def get_today_active_seconds(self) -> float:
        """Calculate active (non-idle) screentime for today.

        Returns:
            float: Active seconds worked at the screen today.
        """
        return max(self._active_seconds_today, 0.0)

    def get_current_session_seconds(self) -> float:
        """Calculate duration of the current login session.

        Returns:
            float: Elapsed seconds in current session.
        """
        if not self.current_session:
            return self._total_seconds_today
        return max(0.0, (datetime.now() - self.current_session.start).total_seconds())

    def get_last_session_seconds(self) -> float:
        """Calculate duration of the previous login session.

        Returns:
            float: Duration in seconds of last session.
        """
        if not self.last_session:
            return 0.0
        return float(self.last_session.duration_seconds)

    def get_today_intervals(self) -> list[tuple[float, float]]:
        """Get list of (start_hour, end_hour) floating intervals active today on 24h dial.

        Returns:
            list[tuple[float, float]]: Hour intervals (0.0 to 24.0) active today.
        """
        now = datetime.now()
        today_date = now.date()
        intervals: list[tuple[float, float]] = []

        # 1. Completed sessions today
        for s in self.today_completed_sessions:
            s_end = s.end or now
            h_start = s.start.hour + (s.start.minute / 60.0) + (s.start.second / 3600.0)
            h_end = s_end.hour + (s_end.minute / 60.0) + (s_end.second / 3600.0)
            if h_end < h_start:
                h_end += 24.0
            intervals.append((h_start, min(24.0, h_end)))

        # 2. Current session today
        if self.current_session:
            start_dt = self.current_session.start
            if start_dt.date() < today_date:
                h_start = 0.0
            else:
                h_start = start_dt.hour + (start_dt.minute / 60.0) + (start_dt.second / 3600.0)
            h_now = now.hour + (now.minute / 60.0) + (now.second / 3600.0)
            intervals.append((h_start, h_now))

        return intervals

    def get_last_session_interval(self) -> tuple[float, float] | None:
        """Get (start_hour, end_hour) interval for the last session on 24h dial.

        Returns:
            tuple[float, float] | None: Normalized 24h start and end hour.
        """
        if not self.last_session or not self.last_session.end:
            return None
        s = self.last_session
        h_start = s.start.hour + (s.start.minute / 60.0) + (s.start.second / 3600.0)
        h_end = s.end.hour + (s.end.minute / 60.0) + (s.end.second / 3600.0)
        if h_end < h_start:
            h_end += 24.0
        return (h_start, min(24.0, h_end))


def format_duration(seconds: float, show_seconds: bool = True) -> str:
    """Format total seconds into human readable duration string (e.g., '06h 58m 20s').

    Args:
        seconds: Duration in seconds.
        show_seconds: If True, includes seconds in the output string.

    Returns:
        str: Formatted duration string.
    """
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if show_seconds:
        return f"{h:02d}h {m:02d}m {s:02d}s"
    return f"{h:02d}h {m:02d}m"
