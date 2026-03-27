"""Timestamp and time-related utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def timestamp_to_datetime(ts: int | float) -> datetime:
    """Convert Unix timestamp (seconds or milliseconds) to datetime."""
    if ts > 1e12:  # Milliseconds
        ts = ts / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def hours_ago(hours: int) -> datetime:
    """Get datetime N hours ago."""
    from datetime import timedelta
    return utcnow() - timedelta(hours=hours)


def days_ago(days: int) -> datetime:
    """Get datetime N days ago."""
    from datetime import timedelta
    return utcnow() - timedelta(days=days)


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"
