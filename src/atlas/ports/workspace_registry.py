"""Persistence ports for canonical Project/Environment associations and Workspaces."""

from typing import Protocol

from atlas.workspace.models import WorkspaceRecord


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

