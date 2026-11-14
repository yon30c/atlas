"""Identity binding contracts for the project-independent Memory Engine.

A binding is evidence returned by a trusted identity authority. It is not
constructed from caller-supplied context fields and does not grant access by
itself; authorization policy must still evaluate ownership and scope.
"""
from dataclasses import dataclass
from typing import Protocol

from atlas.memory.errors import MemoryContractError


@dataclass(frozen=True, slots=True)
class MemoryIdentityBinding:
    """Verified mapping from an authenticated actor to a canonical subject."""

    actor_identity_id: str
    subject_id: str
    is_active: bool
    revision: int

    def __post_init__(self) -> None:
        for field in ("actor_identity_id", "subject_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise MemoryContractError(f"{field} must be a non-empty string")
        if not isinstance(self.is_active, bool):
            raise ValueError("is_active must be bool")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("revision must be a positive integer")


class MemoryIdentityBindingPort(Protocol):
    """Resolves actor-to-subject bindings from an authoritative identity source."""

    def resolve_subject(self, actor_identity_id: str) -> MemoryIdentityBinding | None:
        """Return the verified binding for the exact actor, or None."""


def resolve_authenticated_memory_binding(
    actor_identity_id: str,
    actor_revision: int,
    actor_active: bool,
    binding_port: MemoryIdentityBindingPort,
) -> MemoryIdentityBinding | None:
    """Resolve and validate a binding; malformed or unavailable evidence denies."""
    if not isinstance(actor_identity_id, str) or not actor_identity_id.strip():
        return None
    if isinstance(actor_revision, bool) or not isinstance(actor_revision, int) or actor_revision < 1:
        return None
    if actor_active is not True:
        return None
    if not callable(getattr(binding_port, "resolve_subject", None)):
        return None
    try:
        binding = binding_port.resolve_subject(actor_identity_id)
    except Exception:
        return None
    if not isinstance(binding, MemoryIdentityBinding):
        return None
    if not binding.is_active or binding.actor_identity_id != actor_identity_id:
        return None
    if binding.revision != actor_revision:
        return None
    return binding
