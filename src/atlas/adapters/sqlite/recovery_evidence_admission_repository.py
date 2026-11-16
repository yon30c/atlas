"""SQLite persistence for one-time recovery evidence admission."""

from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.application.recovery_admission import RecoveryEvidenceAdmissionCommand
from atlas.core.errors import ContractError
from atlas.authorization.recovery_evidence_admission_audit import (
    RecoveryEvidenceAdmissionAudit,
    RecoveryEvidenceAdmissionAuditReport,
    RecoveryEvidenceAdmissionAuditStatus,
)
from atlas.ports.recovery_evidence_admission import (
    RecoveryEvidenceAdmissionPort,
    RecoveryEvidenceAdmissionResult,
    RecoveryEvidenceAdmissionStatus,
)


class SQLiteRecoveryEvidenceAdmissionRepository(RecoveryEvidenceAdmissionPort):
    """Persist admission under the shared local-authority BEGIN IMMEDIATE UoW.

    This records evidence admission only. It does not authorize or execute effects.
    """

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        unit_of_work: SQLiteUnitOfWork,
    ) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if not isinstance(unit_of_work, SQLiteUnitOfWork):
            raise ContractError("unit_of_work debe ser SQLiteUnitOfWork")
        self._database = database
        self._unit_of_work = unit_of_work

    def _connection(self) -> sqlite3.Connection:
        return self._unit_of_work._connection_for(self._database)

    @staticmethod
    def _canonical(command: RecoveryEvidenceAdmissionCommand) -> bytes:
        payload = {
            "admission_id": command.admission_id,
            "operation_id": command.operation_id,
            "evidence_id": command.evidence_id,
            "evidence_digest": command.evidence_digest,
            "issuer_id": command.issuer_id,
            "issuer_registry_revision": command.issuer_registry_revision,
            "evidence_kind": command.evidence_kind.value,
            "targets": [
                {
                    "authority_kind": target.authority_kind.value,
                    "authority_id": target.authority_id,
                    "expected_revision": target.expected_revision,
                    "proposed_revision": target.proposed_revision,
                }
                for target in command.targets
            ],
            "requested_at": command.requested_at.isoformat(timespec="microseconds"),
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    @staticmethod
    def _audit_row(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> RecoveryEvidenceAdmissionAudit:
        diagnostics: list[str] = []
        admission_id = row["admission_id"]

        try:
            canonical_bytes = bytes(row["command_canonical"])
            payload = json.loads(canonical_bytes.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("canonical command must be an object")
            recanonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if recanonical != canonical_bytes:
                diagnostics.append("NON_CANONICAL_COMMAND")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            payload = None
            diagnostics.append("INVALID_CANONICAL_COMMAND")

        if hashlib.sha256(bytes(row["command_canonical"])).hexdigest() != row["command_digest"]:
            diagnostics.append("COMMAND_DIGEST_MISMATCH")

        if not isinstance(row["evidence_digest"], str) or (
            len(row["evidence_digest"]) != 64
            or any(char not in "0123456789abcdef" for char in row["evidence_digest"])
        ):
            diagnostics.append("INVALID_EVIDENCE_DIGEST")

        if payload is not None:
            expected = {
                "admission_id": row["admission_id"],
                "operation_id": row["operation_id"],
                "evidence_id": row["evidence_id"],
                "evidence_digest": row["evidence_digest"],
                "issuer_id": row["issuer_id"],
                "issuer_registry_revision": row["issuer_registry_revision"],
                "evidence_kind": row["evidence_kind"],
                "requested_at": row["requested_at"],
            }
            for field, value in expected.items():
                if payload.get(field) != value:
                    diagnostics.append("COLUMN_BINDING_MISMATCH")
                    break

            targets = payload.get("targets")
            if not isinstance(targets, list) or len(targets) != row["target_count"]:
                diagnostics.append("TARGET_COUNT_MISMATCH")
            elif any(
                not isinstance(target, dict)
                or set(target) != {
                    "authority_kind", "authority_id",
                    "expected_revision", "proposed_revision",
                }
                or not isinstance(target.get("authority_kind"), str)
                or not isinstance(target.get("authority_id"), str)
                or not target.get("authority_id", "").strip()
                or isinstance(target.get("expected_revision"), bool)
                or not isinstance(target.get("expected_revision"), int)
                or target["expected_revision"] < 1
                or isinstance(target.get("proposed_revision"), bool)
                or not isinstance(target.get("proposed_revision"), int)
                or target["proposed_revision"] != target["expected_revision"] + 1
                for target in targets
            ):
                diagnostics.append("INVALID_TARGET_BINDING")
            else:
                identities = tuple(
                    (target["authority_kind"], target["authority_id"])
                    for target in targets
                )
                if identities != tuple(sorted(set(identities))):
                    diagnostics.append("NON_CANONICAL_TARGET_SET")
                reserved = connection.execute(
                    """
                    SELECT authority_kind, authority_id, expected_revision, proposed_revision
                    FROM multi_authority_change_targets
                    WHERE operation_id = ?
                    ORDER BY authority_kind, authority_id
                    """,
                    (row["operation_id"],),
                ).fetchall()
                reserved_targets = tuple(
                    (item["authority_kind"], item["authority_id"],
                     item["expected_revision"], item["proposed_revision"])
                    for item in reserved
                )
                supplied_targets = tuple(
                    (target["authority_kind"], target["authority_id"],
                     target["expected_revision"], target["proposed_revision"])
                    for target in targets
                )
                if supplied_targets != reserved_targets:
                    diagnostics.append("OPERATION_TARGET_MISMATCH")

        for field in ("requested_at", "recorded_at"):
            try:
                parsed = datetime.fromisoformat(row[field])
                if (
                    parsed.tzinfo is None
                    or parsed.utcoffset() is None
                    or parsed.utcoffset().total_seconds() != 0
                    or parsed.isoformat(timespec="microseconds") != row[field]
                ):
                    diagnostics.append("NON_CANONICAL_TIMESTAMP")
                    break
            except (TypeError, ValueError, OverflowError):
                diagnostics.append("INVALID_TIMESTAMP")
                break

        codes = tuple(sorted(set(diagnostics)))
        return RecoveryEvidenceAdmissionAudit(
            admission_id=admission_id,
            status=(
                RecoveryEvidenceAdmissionAuditStatus.CORRUPT
                if codes else RecoveryEvidenceAdmissionAuditStatus.HEALTHY
            ),
            diagnostic_codes=codes,
        )

    def audit_admission(
        self,
        admission_id: str,
    ) -> RecoveryEvidenceAdmissionAudit | None:
        if not isinstance(admission_id, str) or not admission_id.strip():
            raise ContractError("admission_id debe ser una cadena no vacía")
        connection = self._connection()
        row = connection.execute(
            "SELECT * FROM recovery_evidence_admissions WHERE admission_id = ?",
            (admission_id,),
        ).fetchone()
        return None if row is None else self._audit_row(connection, row)

    def audit_all(self) -> RecoveryEvidenceAdmissionAuditReport:
        """Audit all persisted receipts from the active UoW read snapshot."""
        connection = self._connection()
        rows = connection.execute(
            "SELECT * FROM recovery_evidence_admissions ORDER BY admission_id"
        ).fetchall()
        audits = tuple(self._audit_row(connection, row) for row in rows)
        return RecoveryEvidenceAdmissionAuditReport(audits)

    def admit(
        self,
        command: RecoveryEvidenceAdmissionCommand,
    ) -> RecoveryEvidenceAdmissionResult:
        if not isinstance(command, RecoveryEvidenceAdmissionCommand):
            raise ContractError("command debe ser RecoveryEvidenceAdmissionCommand")
        connection = self._connection()
        canonical = self._canonical(command)
        digest = hashlib.sha256(canonical).hexdigest()

        existing = connection.execute(
            """
            SELECT admission_id, evidence_id, evidence_digest, command_digest, command_canonical
            FROM recovery_evidence_admissions
            WHERE admission_id = ? OR evidence_id = ?
            """,
            (command.admission_id, command.evidence_id),
        ).fetchall()
        if existing:
            for row in existing:
                stored_canonical = bytes(row["command_canonical"])
                if hashlib.sha256(stored_canonical).hexdigest() != row["command_digest"]:
                    raise sqlite3.DatabaseError(
                        "el recibo de admisión persistido no supera la verificación de integridad"
                    )
            if (
                len(existing) == 1
                and existing[0]["admission_id"] == command.admission_id
                and existing[0]["evidence_digest"] == command.evidence_digest
                and existing[0]["evidence_id"] == command.evidence_id
                and existing[0]["command_digest"] == digest
                and bytes(existing[0]["command_canonical"]) == canonical
            ):
                return RecoveryEvidenceAdmissionResult(
                    RecoveryEvidenceAdmissionStatus.REPLAYED,
                    command.admission_id,
                )
            status = (
                RecoveryEvidenceAdmissionStatus.EVIDENCE_REUSED
                if any(row["evidence_id"] == command.evidence_id for row in existing)
                else RecoveryEvidenceAdmissionStatus.OPERATION_MISMATCH
            )
            return RecoveryEvidenceAdmissionResult(status, command.admission_id)

        issuer = connection.execute(
            """
            SELECT registry_revision, enabled
            FROM recovery_evidence_issuer_registry
            WHERE issuer_id = ?
            ORDER BY registry_revision DESC LIMIT 1
            """,
            (command.issuer_id,),
        ).fetchone()
        if issuer is None or issuer["registry_revision"] != command.issuer_registry_revision:
            return RecoveryEvidenceAdmissionResult(
                RecoveryEvidenceAdmissionStatus.STALE_ISSUER, command.admission_id
            )
        if issuer["enabled"] != 1:
            return RecoveryEvidenceAdmissionResult(
                RecoveryEvidenceAdmissionStatus.ISSUER_DISABLED, command.admission_id
            )

        operation = connection.execute(
            """
            SELECT status FROM multi_authority_change_operations
            WHERE operation_id = ?
            """,
            (command.operation_id,),
        ).fetchone()
        if operation is None or operation["status"] not in {
            "INVALIDATION_PENDING", "SOURCE_PENDING",
            "SOURCE_CONFIRMED", "RECONCILING",
        }:
            return RecoveryEvidenceAdmissionResult(
                RecoveryEvidenceAdmissionStatus.OPERATION_MISMATCH,
                command.admission_id,
            )

        target_rows = connection.execute(
            """
            SELECT authority_kind, authority_id, expected_revision, proposed_revision
            FROM multi_authority_change_targets
            WHERE operation_id = ?
            ORDER BY authority_kind, authority_id
            """,
            (command.operation_id,),
        ).fetchall()
        claim_rows = connection.execute(
            """
            SELECT authority_kind, authority_id
            FROM multi_authority_change_claims
            WHERE operation_id = ?
            ORDER BY authority_kind, authority_id
            """,
            (command.operation_id,),
        ).fetchall()
        expected_targets = tuple(
            (
                row["authority_kind"], row["authority_id"],
                row["expected_revision"], row["proposed_revision"],
            )
            for row in target_rows
        )
        supplied_targets = tuple(
            (
                target.authority_kind.value, target.authority_id,
                target.expected_revision, target.proposed_revision,
            )
            for target in command.targets
        )
        expected_claims = tuple((row[0], row[1]) for row in target_rows)
        supplied_claims = tuple((row[0], row[1]) for row in claim_rows)
        if (
            len(expected_targets) < 2
            or expected_targets != supplied_targets
            or expected_claims != supplied_claims
        ):
            return RecoveryEvidenceAdmissionResult(
                RecoveryEvidenceAdmissionStatus.OPERATION_MISMATCH,
                command.admission_id,
            )

        recorded_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            connection.execute(
                """
                INSERT INTO recovery_evidence_admissions (
                    admission_id, evidence_id, evidence_digest, operation_id, issuer_id,
                    issuer_registry_revision, evidence_kind, target_count,
                    command_digest, command_canonical, requested_at, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.admission_id, command.evidence_id, command.evidence_digest,
                    command.operation_id, command.issuer_id, command.issuer_registry_revision,
                    command.evidence_kind.value, len(command.targets), digest,
                    sqlite3.Binary(canonical),
                    command.requested_at.isoformat(timespec="microseconds"),
                    recorded_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise sqlite3.DatabaseError(
                "la admisión no superó las restricciones transaccionales SQLite"
            ) from exc
        return RecoveryEvidenceAdmissionResult(
            RecoveryEvidenceAdmissionStatus.ADMITTED, command.admission_id
        )
