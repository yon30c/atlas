"""Trusted, deliberately unregistered composition for association lifecycle.

This module is an internal composition seam. It is not imported by runtime,
HTTP, CLI, plugin, or public package entry points.
"""

from datetime import timedelta

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.local_authority_unit_of_work import (
    SQLiteLocalAuthorityUnitOfWork,
    SQLiteLocalAuthorityUnitOfWorkFactory,
)
from atlas.adapters.sqlite.project_environment_lifecycle_association_writer import (
    SQLiteProjectEnvironmentLifecycleAssociationWriter,
)
from atlas.adapters.sqlite.project_environment_lifecycle_ledger import (
    SQLiteProjectEnvironmentLifecycleLedger,
)
from atlas.application.project_environment_lifecycle import (
    ProjectEnvironmentLifecycleService,
)
from atlas.core.errors import ContractError
from atlas.identity.verified_identity_context_service import (
    VerifiedIdentityContextService,
)
from atlas.ports.clock import Clock
from atlas.ports.verified_identity_context_attestor import (
    VerifiedIdentityContextAttestorPort,
)


def build_trusted_project_environment_lifecycle_service(
    *,
    database: SQLiteDatabase,
    clock: Clock,
    attestor: VerifiedIdentityContextAttestorPort,
    realm: str,
    audience: str,
    context_ttl: timedelta,
    unit_of_work_factory: SQLiteLocalAuthorityUnitOfWorkFactory | None = None,
) -> ProjectEnvironmentLifecycleService:
    """Build lifecycle service with the real verifier and a private ledger writer.

    Key provisioning remains the caller's trusted responsibility. The returned
    service is the only capability returned; the ledger factory is closure-local.
    """
    if not isinstance(database, SQLiteDatabase):
        raise ContractError("database debe ser SQLiteDatabase")
    if not callable(getattr(clock, "now", None)):
        raise ContractError("clock debe implementar now()")
    if not callable(getattr(attestor, "sign", None)) or not callable(
        getattr(attestor, "verify", None)
    ):
        raise ContractError("attestor debe implementar sign/verify")

    if unit_of_work_factory is None:
        unit_of_work_factory = SQLiteLocalAuthorityUnitOfWorkFactory(database)
    elif not isinstance(
        unit_of_work_factory,
        SQLiteLocalAuthorityUnitOfWorkFactory,
    ):
        raise ContractError(
            "unit_of_work_factory debe ser SQLiteLocalAuthorityUnitOfWorkFactory"
        )
    elif unit_of_work_factory._database is not database:
        raise ContractError(
            "unit_of_work_factory y database deben compartir la misma instancia SQLite"
        )

    identity_verifier = VerifiedIdentityContextService(
        unit_of_work_factory=unit_of_work_factory,
        clock=clock,
        attestor=attestor,
        realm=realm,
        audience=audience,
        context_ttl=context_ttl,
    )

    def ledger_factory(unit):
        if not isinstance(unit, SQLiteLocalAuthorityUnitOfWork):
            raise ContractError("la composición lifecycle requiere UoW local confiable")
        return SQLiteProjectEnvironmentLifecycleLedger(
            database,
            unit_of_work=unit,
        )

    def association_writer_factory(unit):
        if not isinstance(unit, SQLiteLocalAuthorityUnitOfWork):
            raise ContractError("la composición lifecycle requiere UoW local confiable")
        return SQLiteProjectEnvironmentLifecycleAssociationWriter(
            database,
            unit_of_work=unit,
        )

    return ProjectEnvironmentLifecycleService(
        unit_of_work_factory,
        identity_verifier=identity_verifier,
        clock=clock,
        ledger_factory=ledger_factory,
        association_writer_factory=association_writer_factory,
    )
