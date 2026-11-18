"""Ports for immutable Project/Environment lifecycle audit events."""

from typing import Protocol

from atlas.core.project_environment_lifecycle import ProjectEnvironmentLifecycleEvent
from atlas.workspace.models import ProjectEnvironmentAssociation


class ProjectEnvironmentLifecycleLedgerPort(Protocol):
    """Append/read immutable transition facts inside the caller's UoW."""

    def append_event(self, event: ProjectEnvironmentLifecycleEvent) -> None:
        """Persist exactly one event for the association's new revision."""

    def list_events(
        self, project_id: str, environment_id: str
    ) -> tuple[ProjectEnvironmentLifecycleEvent, ...]:
        """Return the association's audit history in revision order."""


class ProjectEnvironmentLifecycleAssociationWriterPort(Protocol):
    """Narrow persistence capability for one audited association transition."""

    def update_association(
        self,
        association: ProjectEnvironmentAssociation,
        *,
        expected_revision: int,
        lifecycle_event_id: str,
    ) -> None:
        """CAS-update the association as part of the caller's lifecycle UoW."""
