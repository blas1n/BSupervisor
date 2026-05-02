"""Tests for date-window helpers — Audit §M11.

The helpers replace duplicated `datetime(target.year, target.month, target.day, ...)`
constructions in `cost_tracker.py`, `status.py`, `reporter.py`. They MUST always
return timezone-aware UTC bounds with end-of-day inclusive of microseconds, so
existing `WHERE timestamp <= end` queries keep their semantics.
"""

from datetime import date, datetime, timezone

import pytest

from bsupervisor.core.dates import day_window, today_utc, today_window


class TestDayWindow:
    def test_returns_utc_bounds_for_date(self) -> None:
        target = date(2026, 4, 25)
        start, end = day_window(target)

        assert start == datetime(2026, 4, 25, 0, 0, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 4, 25, 23, 59, 59, 999999, tzinfo=timezone.utc)

    def test_start_and_end_are_timezone_aware_utc(self) -> None:
        start, end = day_window(date(2026, 1, 1))
        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_end_minus_start_is_almost_one_day(self) -> None:
        start, end = day_window(date(2026, 4, 25))
        delta = end - start
        # 23:59:59.999999 — one microsecond shy of a full day
        assert delta.days == 0
        assert delta.seconds == 86399
        assert delta.microseconds == 999999

    def test_rejects_naive_datetime_input(self) -> None:
        with pytest.raises(TypeError):
            day_window("2026-04-25")  # type: ignore[arg-type]


class TestTodayWindow:
    def test_uses_current_utc_date(self) -> None:
        start, end = today_window()
        now = datetime.now(timezone.utc)
        assert start.date() == now.date()
        assert end.date() == now.date()
        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc
        assert start.hour == 0 and start.minute == 0 and start.second == 0
        assert end.hour == 23 and end.minute == 59 and end.second == 59


class TestTodayUtc:
    def test_returns_today_in_utc(self) -> None:
        result = today_utc()
        assert isinstance(result, date)
        assert result == datetime.now(timezone.utc).date()
