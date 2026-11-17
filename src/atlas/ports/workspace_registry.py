"""Persistence ports for canonical Project/Environment associations and Workspaces."""

from typing import Protocol

from atlas.memory.models import EnvironmentId, ProjectId
from atlas.workspace.models import (
    ProjectEnvironmentAssociation,
    WorkspaceRecord,
)


class WorkspaceRegistryPort(Protocol):
    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        """Return the canonical workspace record, without resolving its root."""

    def create_workspace(self, workspace: WorkspaceRecord) -> None:
        """Create one workspace with an explicit canonical owner and scope."""

    def update_workspace(
        self, workspace: WorkspaceRecord, *, expected_revision: int
    ) -> None:
        """CAS-update mutable workspace metadata; identity and scope stay fixed."""

    def list_workspaces_by_owner(self, owner_user_id: str) -> tuple[WorkspaceRecord, ...]:
        """List canonical workspace identifiers for one owner."""


class ProjectEnvironmentAssociationPort(Protocol):
    def get_association(
        self, project_id: ProjectId, environment_id: EnvironmentId
    ) -> ProjectEnvironmentAssociation | None:
        """Return the exact Project/Environment association."""

    def create_association(self, association: ProjectEnvironmentAssociation) -> None:
        """Create an explicit association; never infer one from independent records."""

    def update_association(
        self, association: ProjectEnvironmentAssociation, *, expected_revision: int
    ) -> None:
        """CAS-update association status while retaining its identity."""
