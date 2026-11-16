"""SQLite adapter for the append-only recovery-evidence issuer inventory."""

from contextlib import contextmanager
from datetime import datetime
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.authorization.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistration,
)
from atlas.authorization.recovery_evidence_trust_audit import (
    RecoveryEvidenceIssuerInventoryAudit,
    RecoveryEvidenceIssuerInventoryAuditReport,
    RecoveryEvidenceIssuerInventoryAuditStatus,
    RecoveryEvidenceIssuerTrustPolicyAuditStatus,
)
from atlas.adapters.sqlite.recovery_evidence_trust_policy_repository import (
    SQLiteRecoveryEvidenceIssuerTrustPolicyRepository,
)
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.ports.recovery_evidence_issuer_registry import (
    RecoveryEvidenceIssuerRegistryPort,
)


class SQLiteRecoveryEvidenceIssuerRegistryRepository(
    RecoveryEvidenceIssuerRegistryPort
):
    """Append-only issuer inventory with CAS revisions and policy cross-audit."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        unit_of_work: SQLiteUnitOfWork | None = None,
    ) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if unit_of_work is not None and not isinstance(unit_of_work, SQLiteUnitOfWork):
            raise ContractError("unit_of_work debe ser SQLiteUnitOfWork")
        self._database = database
        self._unit_of_work = unit_of_work

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.connection() as connection:
                yield connection

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        if self._unit_of_work is not None:
            yield self._unit_of_work._connection_for(self._database)
        else:
            with self._database.unit_of_work() as unit:
                yield unit._connection_for(self._database)

    @staticmethod
    def _required_issuer(issuer_id: object) -> str:
        if not isinstance(issuer_id, str) or not issuer_id.strip():
            raise ContractError("issuer_id debe ser una cadena no vacía")
        return issuer_id

    @staticmethod
    def _values(
        registration: RecoveryEvidenceIssuerRegistration,
    ) -> tuple[object, ...]:
        if not isinstance(registration, RecoveryEvidenceIssuerRegistration):
            raise ContractError("registration debe ser RecoveryEvidenceIssuerRegistration")
        return (
            registration.issuer_id,
            registration.registry_revision,
            int(registration.enabled),
            registration.changed_at.isoformat(timespec="microseconds"),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RecoveryEvidenceIssuerRegistration:
        try:
            enabled = row["enabled"]
            if isinstance(enabled, bool) or not isinstance(enabled, int) or enabled not in (0, 1):
                raise ValueError("invalid enabled flag")
            return RecoveryEvidenceIssuerRegistration(
                issuer_id=row["issuer_id"],
                registry_revision=row["registry_revision"],
                enabled=bool(enabled),
                changed_at=datetime.fromisoformat(row["changed_at"]),
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError("registro SQLite de emisor corrupto") from exc

    def create(self, registration: RecoveryEvidenceIssuerRegistration) -> None:
        values = self._values(registration)
        if registration.registry_revision != 1:
            raise ContractError("la primera revisión del emisor debe ser 1")
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO recovery_evidence_issuer_registry (
                        issuer_id, registry_revision, enabled, changed_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("no se pudo registrar el emisor") from exc

    def append(
        self,
        registration: RecoveryEvidenceIssuerRegistration,
        *,
        expected_revision: int,
    ) -> None:
        values = self._values(registration)
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")
        if registration.registry_revision != expected_revision + 1:
            raise ContractError("la nueva revisión del registro debe incrementar exactamente una")
        with self._write_connection() as connection:
            current = connection.execute(
                """
                SELECT MAX(registry_revision) AS revision
                FROM recovery_evidence_issuer_registry
                WHERE issuer_id = ?
                """,
                (registration.issuer_id,),
            ).fetchone()["revision"]
            if current is None:
                raise NotFoundError("emisor no registrado")
            if current != expected_revision:
                raise ConcurrencyError("la revisión del registro del emisor cambió")
            try:
                connection.execute(
                    """
                    INSERT INTO recovery_evidence_issuer_registry (
                        issuer_id, registry_revision, enabled, changed_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError("la nueva revisión viola las restricciones SQLite") from exc

    def get_registration(
        self,
        issuer_id: str,
    ) -> RecoveryEvidenceIssuerRegistration | None:
        key = self._required_issuer(issuer_id)
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM recovery_evidence_issuer_registry
                WHERE issuer_id = ?
                ORDER BY registry_revision DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_registrations(self) -> tuple[RecoveryEvidenceIssuerRegistration, ...]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT current.*
                FROM recovery_evidence_issuer_registry AS current
                JOIN (
                    SELECT issuer_id, MAX(registry_revision) AS revision
                    FROM recovery_evidence_issuer_registry
                    GROUP BY issuer_id
                ) AS latest
                  ON latest.issuer_id = current.issuer_id
                 AND latest.revision = current.registry_revision
                ORDER BY current.issuer_id
                """
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def list_history(
        self,
        issuer_id: str,
    ) -> tuple[RecoveryEvidenceIssuerRegistration, ...]:
        key = self._required_issuer(issuer_id)
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recovery_evidence_issuer_registry
                WHERE issuer_id = ?
                ORDER BY registry_revision
                """,
                (key,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _audit_registry_rows(
        issuer_id: str,
        rows: list[sqlite3.Row],
    ) -> tuple[tuple[int, ...], int | None, bool | None, tuple[str, ...]]:
        revisions: list[int] = []
        diagnostics: list[str] = []
        enabled_by_revision: dict[int, bool] = {}
        for row in rows:
            revision = row["registry_revision"]
            if (
                isinstance(revision, bool)
                or not isinstance(revision, int)
                or revision < 1
            ):
                diagnostics.append("INVALID_REGISTRY_REVISION")
                continue
            revisions.append(revision)
            try:
                registration = SQLiteRecoveryEvidenceIssuerRegistryRepository._from_row(row)
                enabled_by_revision[revision] = registration.enabled
                if (
                    registration.changed_at.isoformat(timespec="microseconds")
                    != row["changed_at"]
                ):
                    diagnostics.append("NON_CANONICAL_REGISTRY_RECORD")
            except (ContractError, TypeError, ValueError, KeyError, OverflowError):
                diagnostics.append("INVALID_REGISTRY_RECORD")
        ordered = tuple(sorted(revisions))
        if ordered and ordered != tuple(range(1, ordered[-1] + 1)):
            diagnostics.append("REGISTRY_REVISION_SEQUENCE_GAP")
        latest = ordered[-1] if ordered else None
        return ordered, latest, enabled_by_revision.get(latest), tuple(sorted(set(diagnostics)))

    def audit_inventory(self) -> RecoveryEvidenceIssuerInventoryAuditReport:
        """Cross-audit registry and trust policies from one read snapshot."""
        with self._read_connection() as connection:
            owns_snapshot = self._unit_of_work is None
            if owns_snapshot:
                connection.execute("BEGIN")
            try:
                registry_rows = connection.execute(
                    """
                    SELECT * FROM recovery_evidence_issuer_registry
                    ORDER BY issuer_id, registry_revision
                    """
                ).fetchall()
                policy_rows = connection.execute(
                    """
                    SELECT * FROM recovery_evidence_issuer_trust_policies
                    ORDER BY issuer_id, policy_revision
                    """
                ).fetchall()
            finally:
                if owns_snapshot and connection.in_transaction:
                    connection.rollback()

        registry_groups: dict[str, list[sqlite3.Row]] = {}
        for row in registry_rows:
            registry_groups.setdefault(row["issuer_id"], []).append(row)
        policy_groups: dict[str, list[sqlite3.Row]] = {}
        for row in policy_rows:
            policy_groups.setdefault(row["issuer_id"], []).append(row)

        all_issuers = sorted(set(registry_groups) | set(policy_groups))
        audits: list[RecoveryEvidenceIssuerInventoryAudit] = []
        for issuer_id in all_issuers:
            registered_rows = registry_groups.get(issuer_id, [])
            policy_records = policy_groups.get(issuer_id, [])
            policy_audit = (
                SQLiteRecoveryEvidenceIssuerTrustPolicyRepository._audit_issuer_rows(
                    issuer_id, policy_records
                )
                if policy_records or issuer_id in policy_groups
                else None
            )
            if not registered_rows:
                audits.append(
                    RecoveryEvidenceIssuerInventoryAudit(
                        issuer_id=issuer_id,
                        status=RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_ORPHAN,
                        registry_revisions=(),
                        latest_registry_revision=None,
                        policy_status=(
                            None if policy_audit is None else policy_audit.status
                        ),
                        diagnostic_codes=("POLICY_WITHOUT_REGISTRY",),
                    )
                )
                continue

            revisions, latest, enabled, registry_diagnostics = (
                self._audit_registry_rows(issuer_id, registered_rows)
            )
            diagnostics = list(registry_diagnostics)
            if registry_diagnostics:
                status = RecoveryEvidenceIssuerInventoryAuditStatus.REGISTRY_CORRUPT
            elif enabled is False:
                status = RecoveryEvidenceIssuerInventoryAuditStatus.REGISTRY_DISABLED
                diagnostics.append("ISSUER_DISABLED_IN_REGISTRY")
            elif policy_audit is None or (
                policy_audit.status
                is RecoveryEvidenceIssuerTrustPolicyAuditStatus.MISSING_POLICY
            ):
                status = RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_MISSING
                diagnostics.append("REGISTERED_ISSUER_HAS_NO_POLICY")
            elif policy_audit.status is RecoveryEvidenceIssuerTrustPolicyAuditStatus.CORRUPT:
                status = RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_CORRUPT
                diagnostics.extend(policy_audit.diagnostic_codes)
            elif policy_audit.status is RecoveryEvidenceIssuerTrustPolicyAuditStatus.DISABLED:
                status = RecoveryEvidenceIssuerInventoryAuditStatus.POLICY_DISABLED
                diagnostics.extend(policy_audit.diagnostic_codes)
            else:
                status = RecoveryEvidenceIssuerInventoryAuditStatus.HEALTHY

            audits.append(
                RecoveryEvidenceIssuerInventoryAudit(
                    issuer_id=issuer_id,
                    status=status,
                    registry_revisions=revisions,
                    latest_registry_revision=latest,
                    policy_status=None if policy_audit is None else policy_audit.status,
                    diagnostic_codes=tuple(sorted(set(diagnostics))),
                )
            )

        return RecoveryEvidenceIssuerInventoryAuditReport(tuple(audits))
