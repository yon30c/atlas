"""Shared, fail-closed guard for native authentication attempts."""

from datetime import datetime
from typing import Protocol


class AuthenticationAttemptGuardPort(Protocol):
    """Account-scoped throttling boundary; implementations must be atomic/shared."""

    def is_allowed(
        self, issuer_id: str, login_handle: str, *, at: datetime
    ) -> bool:
        """Return whether another verification attempt may proceed."""

    def record_failure(
        self, issuer_id: str, login_handle: str, *, at: datetime
    ) -> None:
        """Record a failed authentication attempt."""

    def record_success(
        self, issuer_id: str, login_handle: str, *, at: datetime
    ) -> None:
        """Record successful authentication and apply the configured reset policy."""
