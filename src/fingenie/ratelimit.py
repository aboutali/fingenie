"""Per-source rate governor with budgets that persist across process restarts.

A single chokepoint every outbound request passes through. Each source can
declare multiple windows (e.g. Twelve Data 8/min AND 800/day); the daily window
is enforced even across separate CLI invocations because hits are stored in
SQLite. On exhaustion we raise ``RateExhausted`` so the router falls back to the
next source instead of blocking on a daily cap.

Implemented directly on stdlib ``sqlite3`` (sliding-window log) to stay light
and keep full control of the persistence semantics.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class RateExhausted(Exception):
    """Raised when a source has no budget left in one of its windows."""

    def __init__(self, source: str, limit: int, window_seconds: int) -> None:
        self.source = source
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(
            f"rate budget exhausted for {source!r}: {limit} per {window_seconds}s"
        )


class RateGovernor:
    def __init__(
        self,
        db_path: str | Path,
        budgets: dict[str, list[tuple[int, int]]],
        clock=time.time,
    ) -> None:
        self.budgets = budgets
        self._clock = clock
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS hits (source TEXT NOT NULL, ts REAL NOT NULL)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_hits ON hits (source, ts)")

    def _count(self, source: str, since: float) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM hits WHERE source = ? AND ts >= ?", (source, since)
        ).fetchone()
        return int(row[0]) if row else 0

    def acquire(self, source: str) -> None:
        """Reserve one request slot for ``source`` or raise ``RateExhausted``.

        Checks every window first, then records a single hit covering them all.
        """
        windows = self.budgets.get(source)
        if not windows:
            return  # unmetered source
        now = self._clock()
        max_window = max(w for _, w in windows)
        # prune rows older than the largest window to keep the table small
        self._conn.execute(
            "DELETE FROM hits WHERE source = ? AND ts < ?", (source, now - max_window)
        )
        for limit, window_seconds in windows:
            if self._count(source, now - window_seconds) >= limit:
                raise RateExhausted(source, limit, window_seconds)
        self._conn.execute("INSERT INTO hits (source, ts) VALUES (?, ?)", (source, now))

    def remaining(self, source: str) -> dict[str, int]:
        """Remaining slots per window, e.g. {"60s": 53, "86400s": 740}."""
        windows = self.budgets.get(source)
        if not windows:
            return {}
        now = self._clock()
        out: dict[str, int] = {}
        for limit, window_seconds in windows:
            used = self._count(source, now - window_seconds)
            out[f"{window_seconds}s"] = max(0, limit - used)
        return out

    def close(self) -> None:
        self._conn.close()
