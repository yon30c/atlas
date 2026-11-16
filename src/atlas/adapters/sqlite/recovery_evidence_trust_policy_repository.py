"""SQLite persistence adapter for immutable recovery-evidence issuer policies."""

from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3
from typing import Iterator

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.authorization.recovery_evidence_trust import (
    RecoveryEvidenceIssuerTrustPolicy,
)
from atlas.authorization.recovery_evidence_trust_audit import (
    RecoveryEvidenceIssuerTrustPolicyAudit,
    RecoveryEvidenceIssuerTrustPolicyAuditReport,
    RecoveryEvidenceIssuerTrustPolicyAuditStatus,
)
from atlas.core.errors import ConcurrencyError, ContractError, NotFoundError
from atlas.memory.authority_changes import MultiAuthorityRecoveryEvidenceKind
from atlas.ports.recovery_evidence_issuer_trust import (
    RecoveryEvidenceIssuerTrustPolicyPort,
)


class SQLiteRecoveryEvidenceIssuerTrustPolicyRepository(
    RecoveryEvidenceIssuerTrustPolicyPort
):
    """Append-only authoritative policy snapshots, scoped by issuer and revision."""

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
    def _from_row(row: sqlite3.Row) -> RecoveryEvidenceIssuerTrustPolicy:
        try:
            raw_kinds = json.loads(row["allowed_evidence_kinds_json"])
            if (
                not isinstance(raw_kinds, list)
                or not raw_kinds
                or any(not isinstance(item, str) for item in raw_kinds)
            ):
                raise ValueError("invalid evidence kinds")
            kinds = tuple(MultiAuthorityRecoveryEvidenceKind(item) for item in raw_kinds)
            return RecoveryEvidenceIssuerTrustPolicy(
                issuer_id=row["issuer_id"],
                policy_revision=row["policy_revision"],
                enabled=bool(row["enabled"]),
                allowed_evidence_kinds=kinds,
                valid_from=datetime.fromisoformat(row["valid_from"]),
                valid_until=(
                    None if row["valid_until"] is None
                    else datetime.fromisoformat(row["valid_until"])
                ),
                max_evidence_lifetime_seconds=row["max_evidence_lifetime_seconds"],
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ContractError("registro SQLite de política de confianza corrupto") from exc

    @staticmethod
    def _values(policy: RecoveryEvidenceIssuerTrustPolicy) -> tuple[object, ...]:
        if not isinstance(policy, RecoveryEvidenceIssuerTrustPolicy):
            raise ContractError("policy debe ser RecoveryEvidenceIssuerTrustPolicy")
        return (
            policy.issuer_id,
            policy.policy_revision,
            int(policy.enabled),
            json.dumps(
                [kind.value for kind in policy.allowed_evidence_kinds],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            policy.valid_from.isoformat(timespec="microseconds"),
            None if policy.valid_until is None
            else policy.valid_until.isoformat(timespec="microseconds"),
            policy.max_evidence_lifetime_seconds,
        )

    def create(self, policy: RecoveryEvidenceIssuerTrustPolicy) -> None:
        values = self._values(policy)
        if policy.policy_revision != 1:
            raise ContractError("la primera política de un emisor debe tener revisión 1")
        try:
            with self._write_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO recovery_evidence_issuer_trust_policies (
                        issuer_id, policy_revision, enabled,
                        allowed_evidence_kinds_json, valid_from, valid_until,
                        max_evidence_lifetime_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise ContractError("no se pudo crear la política inicial del emisor") from exc

    def append(
        self,
        policy: RecoveryEvidenceIssuerTrustPolicy,
        *,
        expected_revision: int,
    ) -> None:
        values = self._values(policy)
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ContractError("expected_revision debe ser un entero positivo")
        if policy.policy_revision != expected_revision + 1:
            raise ContractError("la nueva política debe incrementar exactamente una revisión")
        with self._write_connection() as connection:
            current = connection.execute(
                """
                SELECT MAX(policy_revision) AS revision
                FROM recovery_evidence_issuer_trust_policies
                WHERE issuer_id = ?
                """,
                (policy.issuer_id,),
            ).fetchone()["revision"]
            if current is None:
                raise NotFoundError("política de confianza del emisor no encontrada")
            if current != expected_revision:
                raise ConcurrencyError("la revisión de la política de confianza cambió")
            try:
                connection.execute(
                    """
                    INSERT INTO recovery_evidence_issuer_trust_policies (
                        issuer_id, policy_revision, enabled,
                        allowed_evidence_kinds_json, valid_from, valid_until,
                        max_evidence_lifetime_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError("la nueva política viola las restricciones SQLite") from exc

    def get_policy(
        self,
        issuer_id: str,
    ) -> RecoveryEvidenceIssuerTrustPolicy | None:
        key = self._required_issuer(issuer_id)
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM recovery_evidence_issuer_trust_policies
                WHERE issuer_id = ?
                ORDER BY policy_revision DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_history(
        self,
        issuer_id: str,
    ) -> tuple[RecoveryEvidenceIssuerTrustPolicy, ...]:
        key = self._required_issuer(issuer_id)
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recovery_evidence_issuer_trust_policies
                WHERE issuer_id = ?
                ORDER BY policy_revision
                """,
                (key,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _audit_issuer_rows(
        issuer_id: str,
        rows: list[sqlite3.Row],
    ) -> RecoveryEvidenceIssuerTrustPolicyAudit:
        if not rows:
            return RecoveryEvidenceIssuerTrustPolicyAudit(
                issuer_id=issuer_id,
                status=RecoveryEvidenceIssuerTrustPolicyAuditStatus.MISSING_POLICY,
                revisions=(),
                latest_revision=None,
                diagnostic_codes=("NO_POLICY_REGISTERED",),
            )

        revisions: list[int] = []
        diagnostics: list[str] = []
        decoded: list[RecoveryEvidenceIssuerTrustPolicy] = []
        for row in rows:
            revision = row["policy_revision"]
            if (
                isinstance(revision, bool)
                or not isinstance(revision, int)
                or revision < 1
            ):
                diagnostics.append("INVALID_REVISION_VALUE")
                continue
            revisions.append(revision)
            enabled = row["enabled"]
            if isinstance(enabled, bool) or not isinstance(enabled, int) or enabled not in (0, 1):
                diagnostics.append("INVALID_ENABLED_VALUE")
            try:
                policy = SQLiteRecoveryEvidenceIssuerTrustPolicyRepository._from_row(row)
                decoded.append(policy)
                canonical_values = SQLiteRecoveryEvidenceIssuerTrustPolicyRepository._values(policy)
                stored_values = (
                    row["issuer_id"],
                    row["policy_revision"],
                    row["enabled"],
                    row["allowed_evidence_kinds_json"],
                    row["valid_from"],
                    row["valid_until"],
                    row["max_evidence_lifetime_seconds"],
                )
                if canonical_values != stored_values:
                    diagnostics.append("NON_CANONICAL_POLICY_RECORD")
            except (ContractError, TypeError, ValueError, KeyError, OverflowError):
                diagnostics.append("INVALID_POLICY_RECORD")

        ordered_revisions = tuple(sorted(revisions))
        if ordered_revisions and ordered_revisions != tuple(
            range(1, ordered_revisions[-1] + 1)
        ):
            diagnostics.append("REVISION_SEQUENCE_GAP")

        latest_revision = ordered_revisions[-1] if ordered_revisions else None
        latest_policy = next(
            (policy for policy in decoded if policy.policy_revision == latest_revision),
            None,
        )
        if diagnostics:
            status = RecoveryEvidenceIssuerTrustPolicyAuditStatus.CORRUPT
        elif latest_policy is not None and not latest_policy.enabled:
            status = RecoveryEvidenceIssuerTrustPolicyAuditStatus.DISABLED
            diagnostics.append("LATEST_POLICY_DISABLED")
        else:
            status = RecoveryEvidenceIssuerTrustPolicyAuditStatus.HEALTHY

        return RecoveryEvidenceIssuerTrustPolicyAudit(
            issuer_id=issuer_id,
            status=status,
            revisions=ordered_revisions,
            latest_revision=latest_revision,
            diagnostic_codes=tuple(sorted(set(diagnostics))),
        )

    def audit_issuer(
        self,
        issuer_id: str,
    ) -> RecoveryEvidenceIssuerTrustPolicyAudit:
        """Audit one issuer, including an explicit result when it has no policy."""
        key = self._required_issuer(issuer_id)
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recovery_evidence_issuer_trust_policies
                WHERE issuer_id = ?
                ORDER BY policy_revision
                """,
                (key,),
            ).fetchall()
        return self._audit_issuer_rows(key, rows)

    def audit_all(
        self,
    ) -> RecoveryEvidenceIssuerTrustPolicyAuditReport:
        """Audit every registered issuer without changing any database state."""
        with self._read_connection() as connection:
            issuer_rows = connection.execute(
                """
                SELECT DISTINCT issuer_id
                FROM recovery_evidence_issuer_trust_policies
                ORDER BY issuer_id
                """
            ).fetchall()
            audits = []
            for issuer_row in issuer_rows:
                issuer_id = issuer_row["issuer_id"]
                rows = connection.execute(
                    """
                    SELECT * FROM recovery_evidence_issuer_trust_policies
                    WHERE issuer_id = ?
                    ORDER BY policy_revision
                    """,
                    (issuer_id,),
                ).fetchall()
                audits.append(self._audit_issuer_rows(issuer_id, rows))
        return RecoveryEvidenceIssuerTrustPolicyAuditReport(tuple(audits))
