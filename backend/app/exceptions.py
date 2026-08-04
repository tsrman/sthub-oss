"""Application-specific exceptions."""

from __future__ import annotations


class QuotaExceededError(Exception):
    """Raised when a user or streamlit quota limit is exceeded."""

    def __init__(
        self,
        message: str,
        limit: int,
        current: int,
        code: str = "quota_exceeded",
    ):
        self.code = code
        self.limit = limit
        self.current = current
        super().__init__(message)


class NotInGroupError(Exception):
    """Raised when the authenticated user is not in any allowed group."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


__all__ = ["QuotaExceededError", "NotInGroupError"]
