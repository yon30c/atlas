"""Coherent revision-validation contract for protected Memory Engine reads.

The result describes authoritative facts. It is not, by itself, a concurrency
barrier: admission and every revision-changing operation must share the
invalidation-first ordering protocol documented by this port.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError
from atlas.memory.consistency import AuthorizationRevisionSet, AuthorizationSnapshot


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _utc(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError(f"{field} debe ser un datetime UTC")


class RevisionValidationStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RevisionValidationResult:
    """Validation outcome bound to one CAM snapshot and its exact revision set."""

    snapshot_id: str
    expected_revisions: AuthorizationRevisionSet
    status: RevisionValidationStatus
    checked_at: datetime
    current_revisions: AuthorizationRevisionSet | None = None

    def __post_init__(self) -> None:
        _required(self.snapshot_id, "snapshot_id")
        if not isinstance(self.expected_revisions, AuthorizationRevisionSet):
            raise ContractError("expected_revisions debe ser AuthorizationRevisionSet")
        if not isinstance(self.status, RevisionValidationStatus):
            raise ContractError("status debe ser RevisionValidationStatus")
        _utc(self.checked_at, "checked_at")

        if self.status is RevisionValidationStatus.CURRENT:
            if self.current_revisions != self.expected_revisions:
                raise ContractError("CURRENT requiere igualdad exacta de todas las revisiones")
        elif self.status is RevisionValidationStatus.STALE:
            if not isinstance(self.current_revisions, AuthorizationRevisionSet):
                raise ContractError("STALE requiere las revisiones autoritativas actuales")
            if self.current_revisions == self.expected_revisions:
                raise ContractError("STALE requiere al menos una revisión diferente")
        elif self.current_revisions is not None:
            raise ContractError("REJECTED/UNAVAILABLE no pueden exponer revisiones actuales")

    @classmethod
    def current(
        cls,
        snapshot: AuthorizationSnapshot,
        checked_at: datetime,
    ) -> "RevisionValidationResult":
        if not isinstance(snapshot, AuthorizationSnapshot):
            raise ContractError("snapshot debe ser AuthorizationSnapshot")
        return cls(
            snapshot_id=snapshot.snapshot_id,
            expected_revisions=snapshot.revisions,
            status=RevisionValidationStatus.CURRENT,
            checked_at=checked_at,
            current_revisions=snapshot.revisions,
        )


class RevisionValidationPort(Protocol):
    """Validate all revisions and current eligibility represented by a CAM snapshot.

    CURRENT means that every required authority still reports the exact
    revision in the snapshot, the memory/version remain readable, the identity
    and PROJECT resources remain active, and any PROJECT Grant is still valid
    at the supplied UTC instant. An expired/revoked/ineligible snapshot is
    REJECTED; a changed revision is STALE; missing, inconsistent or unavailable
    authoritative evidence is UNAVAILABLE.

    IMPORTANT: a point-in-time read alone cannot close the race with a
    concurrent revision change. Implementations are admissible only when every
    mutation first enters the shared invalidation/fencing authority, and the
    admission coordinator serializes its journal append against that intent.
    If the source cannot prove this ordering (or participate in the same
    transaction), it must return UNAVAILABLE. Eventual notifications and
    process-local locks are insufficient.
    """

    def validate_snapshot(
        self,
        snapshot: AuthorizationSnapshot,
        now: datetime,
    ) -> RevisionValidationResult:
        """Return an exact, fail-closed result for the supplied CAM snapshot."""
