"""Pure builder for the owner-approved initial Workspace CAM grant profile.

This module creates grant records only. It does not authenticate an operator,
verify bootstrap evidence, persist authority, or authorize runtime operations.
Those responsibilities belong to the future bootstrap coordinator.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from atlas.workspace.resource_ids import (
    is_canonical_relative_file_path,
    workspace_file_resource_id,
)

from atlas.authorization.models import Grant, GrantResourceScope
from atlas.core.errors import ContractError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity, validate_canonical_uuid4


INITIAL_WORKSPACE_GRANT_TTL = timedelta(days=7)
WORKSPACE_LIST_ACTION = "workspace.list"
WORKSPACE_READ_ACTION = "workspace.read"


@dataclass(frozen=True, slots=True)
class InitialWorkspaceGrantDescriptor:
    """Exact, already-confirmed identifiers and file allowlist for operation B."""

    project_id: str
    environment_id: str
    workspace_id: str
    list_grant_id: str
    read_grant_id: str | None
    selected_file_paths: tuple[str, ...]
    issued_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "project_id",
            "environment_id",
            "workspace_id",
            "list_grant_id",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or not value
                or value.strip() != value
            ):
                raise ContractError(f"{field} debe ser texto no vacío y normalizado")
        if "*" in self.workspace_id or "?" in self.workspace_id:
            raise ContractError("workspace_id no admite wildcards")
        validate_canonical_uuid4(self.list_grant_id, "list_grant_id")
        if self.read_grant_id is not None:
            validate_canonical_uuid4(self.read_grant_id, "read_grant_id")
        if self.read_grant_id == self.list_grant_id:
            raise ContractError("los IDs de Grant deben ser distintos")
        if not isinstance(self.selected_file_paths, tuple):
            raise ContractError("selected_file_paths debe ser una tupla")
        if any(
            not isinstance(path, str) or not is_canonical_relative_file_path(path)
            for path in self.selected_file_paths
        ):
            raise ContractError("la allowlist contiene una ruta no permitida")
        if len(self.selected_file_paths) != len(set(self.selected_file_paths)):
            raise ContractError("la allowlist no puede contener rutas duplicadas")
        if bool(self.selected_file_paths) != (self.read_grant_id is not None):
            raise ContractError(
                "read_grant_id debe existir exactamente cuando hay archivos seleccionados"
            )
        if (
            not isinstance(self.issued_at, datetime)
            or self.issued_at.tzinfo is None
            or self.issued_at.utcoffset() != timedelta(0)
        ):
            raise ContractError("issued_at debe ser un datetime UTC")



def build_initial_workspace_grants(
    owner: CanonicalUserIdentity,
    descriptor: InitialWorkspaceGrantDescriptor,
) -> tuple[Grant, ...]:
    """Build the exact one- or two-Grant package for initial Workspace access.

    The caller must obtain the canonical owner from Identity Authority after
    verifying the operation-B proof inside the same transaction that persists
    both returned Grants. Passing this DTO is not proof of authority.
    """
    if not isinstance(owner, CanonicalUserIdentity):
        raise ContractError("owner debe ser CanonicalUserIdentity")
    if (
        owner.identity.kind is not IdentityKind.USER
        or owner.identity.status is not IdentityStatus.ACTIVE
    ):
        raise ContractError("el propietario debe ser una Identity(USER) activa")
    if not isinstance(descriptor, InitialWorkspaceGrantDescriptor):
        raise ContractError("descriptor debe ser InitialWorkspaceGrantDescriptor")
    validate_canonical_uuid4(owner.user_id, "owner.user_id")
    validate_canonical_uuid4(owner.identity.identity_id, "owner.identity_id")

    expires_at = descriptor.issued_at + INITIAL_WORKSPACE_GRANT_TTL
    listing = Grant(
        grant_id=descriptor.list_grant_id,
        owner_user_id=owner.user_id,
        subject_identity_id=owner.identity.identity_id,
        project_id=descriptor.project_id,
        environment=descriptor.environment_id,
        resource_scope=GrantResourceScope(
            resource_type="workspace",
            resource_ids=frozenset({descriptor.workspace_id}),
        ),
        actions=frozenset({WORKSPACE_LIST_ACTION}),
        issued_at=descriptor.issued_at,
        expires_at=expires_at,
    )
    grants = [listing]
    if descriptor.selected_file_paths:
        reading = Grant(
            grant_id=descriptor.read_grant_id,
            owner_user_id=owner.user_id,
            subject_identity_id=owner.identity.identity_id,
            project_id=descriptor.project_id,
            environment=descriptor.environment_id,
            resource_scope=GrantResourceScope(
                resource_type="workspace_file",
                resource_ids=frozenset(
                    workspace_file_resource_id(descriptor.workspace_id, path)
                    for path in descriptor.selected_file_paths
                ),
            ),
            actions=frozenset({WORKSPACE_READ_ACTION}),
            issued_at=descriptor.issued_at,
            expires_at=expires_at,
        )
        grants.append(reading)
    return tuple(grants)
