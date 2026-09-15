"""Exceptions that tell the worker how to handle a failed job."""

from datetime import datetime


class RateLimitedError(Exception):
    """An external API refused requests until `reset_at`.

    The job is retried at that time without using up an attempt.
    """

    def __init__(self, service: str, reset_at: datetime) -> None:
        super().__init__(f"{service} rate limit reached; retry after {reset_at.isoformat()}")
        self.service = service
        self.reset_at = reset_at


class PermanentJobError(Exception):
    """Retrying cannot help (e.g. a missing API key), so the job fails immediately."""
