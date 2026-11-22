"""Atomic reservation contract for shared native-authentication throttling."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticationAttemptReservation:
    """Opaque, short-lived permission to perform exactly one verification."""

    reservation_id: str
    expires_at: datetime

    def __repr__(self) -> str:
        return "AuthenticationAttemptReservation(<redacted>)"


class AuthenticationAttemptDenied(Exception):
    """No verification slot is currently available for this account."""


class AuthenticationAttemptReservationError(Exception):
    """A reservation is missing, expired, or has already been completed."""


class AuthenticationAttemptGuardPort(Protocol):
    """Atomic, cross-process account-scoped attempt reservation boundary."""

    def begin_attempt(
        self, issuer_id: str, login_handle: str, *, at: datetime
    ) -> AuthenticationAttemptReservation:
        """Reserve one of the account's bounded concurrent verification slots."""

    def complete_failure(
        self, reservation: AuthenticationAttemptReservation, *, at: datetime
    ) -> None:
        """Consume a live reservation and durably record one failed verification."""

    def complete_success(
        self, reservation: AuthenticationAttemptReservation, *, at: datetime
    ) -> None:
        """Consume a live reservation and clear this account's failure history."""

    def abandon_attempt(
        self, reservation: AuthenticationAttemptReservation
    ) -> None:
        """Release a reservation without recording a failed verification."""
