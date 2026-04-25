"""Date-window helpers for time-bucketed aggregations.

Audit §M11 — `cost_tracker.py`, `status.py`, `reporter.py` all built UTC
day boundaries by hand (`datetime(d.year, d.month, d.day, tzinfo=...)`) with
slight variations. Centralizing avoids drift (e.g. forgetting microseconds
on the upper bound, which would silently exclude the last fraction of a
second of activity from end-of-day reports).
"""

from datetime import date, datetime, timezone

__all__ = ["day_window", "today_utc", "today_window"]


def day_window(target: date) -> tuple[datetime, datetime]:
    """Return ``(start, end)`` UTC datetimes covering the full calendar day.

    ``start`` is midnight UTC; ``end`` is 23:59:59.999999 UTC on the same
    date. Both are timezone-aware. Suitable for ``WHERE timestamp >= start
    AND timestamp <= end`` filters used by the status, costs and reporter
    queries.
    """
    if not isinstance(target, date):  # ``datetime`` subclasses ``date``, ok
        raise TypeError(f"target must be a datetime.date, got {type(target).__name__}")
    start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    end = datetime(target.year, target.month, target.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return start, end


def today_utc() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()


def today_window() -> tuple[datetime, datetime]:
    """Return the day-window for today (UTC). Convenience wrapper."""
    return day_window(today_utc())
