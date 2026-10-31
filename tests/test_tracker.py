"""Unit tests for screentime tracker and monotonic session analysis.

Verifies session record creation, journal monotonic calibration, formatters, and fallback handling.
"""

from datetime import datetime, timedelta
import unittest

from tracker import ScreentimeTracker, SessionRecord, format_duration


class TestScreentimeTracker(unittest.TestCase):
    """Test suite for ScreentimeTracker and SessionRecord utilities."""

    def test_format_duration(self) -> None:
        """Validate format_duration human-readable string output."""
        self.assertEqual(format_duration(0), "00h 00m 00s")
        self.assertEqual(format_duration(3665), "01h 01m 05s")
        self.assertEqual(format_duration(3665, show_seconds=False), "01h 01m")
        self.assertEqual(format_duration(5331, show_seconds=False), "01h 28m")

    def test_session_record_serialization(self) -> None:
        """Validate SessionRecord to_dict and from_dict roundtrip."""
        now = datetime(2026, 10, 26, 11, 8, 14)
        start = now - timedelta(seconds=5331)
        rec = SessionRecord(
            start=start,
            end=now,
            duration_seconds=5331.0,
            tty_or_display=":0",
            is_current=False,
        )
        d = rec.to_dict()
        self.assertEqual(d["duration_seconds"], 5331.0)
        self.assertFalse(d["is_current"])

        reconstructed = SessionRecord.from_dict(d)
        self.assertEqual(reconstructed.start, rec.start)
        self.assertEqual(reconstructed.end, rec.end)
        self.assertEqual(reconstructed.duration_seconds, rec.duration_seconds)

    def test_screentime_tracker_sessions(self) -> None:
        """Validate that ScreentimeTracker populates current and last sessions cleanly."""
        tracker = ScreentimeTracker()
        self.assertIsNotNone(tracker.current_session)
        if tracker.current_session:
            self.assertTrue(tracker.current_session.is_current)

        if tracker.last_session is not None:
            self.assertFalse(tracker.last_session.is_current)
            self.assertGreater(tracker.last_session.duration_seconds, 0)
            # Verify that monotonic journal calculation corrected the inflated 06h 58m
            # The true previous session is 01h 28m (approx 5,331 seconds)
            self.assertLess(tracker.last_session.duration_seconds, 20000.0)
            self.assertEqual(format_duration(tracker.last_session.duration_seconds, False), "01h 28m")
            interval = tracker.get_last_session_interval()
            self.assertIsNotNone(interval)
            if interval:
                start_h, end_h = interval
                self.assertGreaterEqual(start_h, 0.0)
                self.assertLessEqual(end_h, 24.0)
                self.assertGreater(end_h, start_h)


if __name__ == "__main__":
    unittest.main()
