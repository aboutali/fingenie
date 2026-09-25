"""Exception hierarchy shared across the engine."""

from __future__ import annotations


class FinGenieError(Exception):
    """Base class for all fingenie errors."""


class SourceError(FinGenieError):
    """A source adapter failed to satisfy a request."""


class TransientError(SourceError):
    """A retryable failure (timeout, connection error, 5xx, 429)."""


class DataNotFound(SourceError):
    """The source responded but has no data for this request (not retryable)."""


class NoSourceAvailable(FinGenieError):
    """No capable source could satisfy the request (all failed or none registered)."""

    def __init__(self, message: str, attempts: list | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []
