"""Test-only helper for creating explicit canonical Project/Environment links."""

from datetime import datetime, timezone
from uuid import uuid4

from atlas.adapters.sqlite.project_environment_association_provisioning_writer import (
    SQLiteProjectEnvironmentAssociationProvisioningWriter,
)
from atlas.core.project_environment_association_provisioning import (
    ProjectEnvironmentAssociationProvisioningProvenance,
    ProjectEnvironmentAssociationProvisioningRequest,
)
from atlas.workspace.models import ProjectEnvironmentAssociation


def provision_association(database, association: ProjectEnvironmentAssociation, *, unit_of_work=None):
    writer = SQLiteProjectEnvironmentAssociationProvisioningWriter(
        database, unit_of_work=unit_of_work
    )
    request = ProjectEnvironmentAssociationProvisioningRequest(
        operation_id=str(uuid4()),
        project_id=association.project_id,
        environment_id=association.environment_id,
        reason="Controlled test fixture provisioning",
    )
    provenance = ProjectEnvironmentAssociationProvisioningProvenance(
        event_id=str(uuid4()),
        real_uid=1000,
        effective_uid=0,
        terminal_id="/dev/pts/test",
        occurred_at=datetime.now(timezone.utc),
    )
    return writer.create_association(request, provenance)
