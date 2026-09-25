"""Small shared parsing helpers used by adapters."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


def to_decimal(x: Any) -> Decimal | None:
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def ms_to_dt(ms: int | float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def secs_to_dt(s: int | float) -> datetime:
    return datetime.fromtimestamp(s, tz=UTC)


def parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def parse_dt(s: str) -> datetime:
    """Parse common ISO-ish timestamps to a tz-aware UTC datetime."""
    cleaned = s.strip().replace("T", " ")
    candidates = (cleaned, cleaned[:19], cleaned[:16], cleaned[:10])
    for cand in candidates:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(cand, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
    return datetime.combine(parse_date(s), datetime.min.time()).replace(tzinfo=UTC)


def today() -> date:
    return datetime.now(tz=UTC).date()


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def iso(d: date) -> str:
    return d.isoformat()


# range string ("1mo", "1y", "6mo", "5d", "ytd", "max") -> a start date
_RANGE_DAYS = {
    "1d": 1, "5d": 5, "1w": 7, "1mo": 31, "3mo": 92, "6mo": 183,
    "1y": 366, "2y": 731, "5y": 1827, "10y": 3653, "max": 36525,
}


def range_to_start(range_str: str, end: date | None = None) -> date:
    end = end or today()
    if range_str.lower() == "ytd":
        return date(end.year, 1, 1)
    days = _RANGE_DAYS.get(range_str.lower(), 366)
    return end - timedelta(days=days)
