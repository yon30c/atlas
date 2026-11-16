"""Durable SQLite primitives for generic authority-change reservations.

This store is deliberately not the authority coordinator: it does not calculate
affected admissions, fence delivery routes, mutate authority sources, or claim
reconciliation. Those operations must be composed by the single consistency
authority inside the same SQLiteUnitOfWork.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.core.errors import ContractError
from atlas.memory.authority_changes import (
    AuthorityChangeIntent,
    AuthorityChangeReservation,
    AuthorityChangeResult,
    AuthorityChangeStatus,
    AuthorityChangeTarget,
    AuthorityChangeTargetKind,
    MultiAuthorityChangeIntent,
    MultiAuthorityChangeReservation,
    AuthorityChangeTerminalEvidence,
    AuthorityChangeTerminalOutcome,
    AuthorityChangeTerminalTarget,
    MultiAuthorityClaimAudit,
    MultiAuthorityClaimAuditStatus,
)
from atlas.memory.consistency import AuthorityKind


def _utc_text(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContractError("datetime debe estar en UTC")
    return value.isoformat(timespec="microseconds")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError("timestamp SQLite no está en UTC")
    return parsed


def _intent_projection(intent: AuthorityChangeIntent) -> dict[str, object]:
    """Semantic idempotency projection; requested_at remains first-write metadata."""
    return {
        "authority_id": intent.authority_id,
        "authority_kind": intent.authority_kind.value,
        "change_kind": intent.change_kind,
        "consumer_id": intent.consumer_id,
        "expected_revision": intent.expected_revision,
        "idempotency_key": intent.idempotency_key,
        "proposed_revision": intent.proposed_revision,
        "request_context_ref": intent.request_context_ref,
    }


def _canonical_intent(intent: AuthorityChangeIntent) -> bytes:
    return json.dumps(
        _intent_projection(intent),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _multi_intent_projection(intent: MultiAuthorityChangeIntent) -> dict[str, object]:
    return {
        "action": intent.action,
        "actor_identity_id": intent.actor_identity_id,
        "consumer_id": intent.consumer_id,
        "environment_id": intent.environment_id,
        "idempotency_key": intent.idempotency_key,
        "owner_id": intent.owner_id,
        "project_id": intent.project_id,
        "request_context_ref": intent.request_context_ref,
        "targets": [
            {
                "authority_id": target.authority_id,
                "authority_kind": target.authority_kind.value,
                "expected_revision": target.expected_revision,
                "proposed_revision": target.proposed_revision,
            }
            for target in intent.targets
        ],
    }


def _canonical_multi_intent(intent: MultiAuthorityChangeIntent) -> bytes:
    return json.dumps(
        _multi_intent_projection(intent),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_terminal_evidence(evidence: AuthorityChangeTerminalEvidence) -> bytes:
    projection = {
        "evidence_id": evidence.evidence_id,
        "operation_id": evidence.operation_id,
        "outcome": evidence.outcome.value,
        "evidence_ref": evidence.evidence_ref,
        "recorded_by": evidence.recorded_by,
        "recorded_at": _utc_text(evidence.recorded_at),
        "targets": [
            {
                "authority_kind": target.authority_kind.value,
                "authority_id": target.authority_id,
                "expected_revision": target.expected_revision,
                "proposed_revision": target.proposed_revision,
                "observed_revision": target.observed_revision,
            }
            for target in evidence.targets
        ],
    }
    return json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")



class SQLiteAuthorityChangeStore:
    """Persists operation identity and semantic idempotency in one SQLite UoW.

    A store is bound to one exact SQLiteDatabase instance. It stores only
    generic control-plane metadata and does not import consumer authority models.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _reservation(row: sqlite3.Row) -> AuthorityChangeReservation:
        intent = AuthorityChangeIntent(
            idempotency_key=row["idempotency_key"],
            consumer_id=row["consumer_id"],
            authority_kind=AuthorityKind(row["authority_kind"]),
            authority_id=row["authority_id"],
            expected_revision=row["expected_revision"],
            proposed_revision=row["proposed_revision"],
            change_kind=row["change_kind"],
            request_context_ref=row["request_context_ref"],
            requested_at=_parse_utc(row["requested_at"]),
        )
        return AuthorityChangeReservation(
            operation_id=row["operation_id"],
            intent=intent,
            status=AuthorityChangeStatus(row["status"]),
        )

    @staticmethod
    def _result(row: sqlite3.Row) -> AuthorityChangeResult | None:
        status = AuthorityChangeStatus(row["status"])
        source_revision = row["source_revision"]
        invalidation_id = row["invalidation_id"]
        if status is AuthorityChangeStatus.ABORTED:
            if source_revision != row["expected_revision"]:
                return None
        if status is AuthorityChangeStatus.COMPLETED:
            if (
                source_revision != row["proposed_revision"]
                or not invalidation_id
            ):
                return None
        return AuthorityChangeResult(
            operation_id=row["operation_id"],
            authority_kind=AuthorityKind(row["authority_kind"]),
            authority_id=row["authority_id"],
            status=status,
            previous_revision=row["expected_revision"],
            proposed_revision=row["proposed_revision"],
            source_revision=source_revision,
            invalidation_id=invalidation_id,
        )

    @staticmethod
    def _select_operation(connection, operation_id: str):
        return connection.execute(
            """
            SELECT o.*, i.idempotency_key
            FROM authority_change_operations AS o
            JOIN authority_change_idempotency AS i
              ON i.operation_id = o.operation_id
            WHERE o.operation_id = ?
            """,
            (operation_id,),
        ).fetchone()

    def reserve_change(
        self,
        intent: AuthorityChangeIntent,
    ) -> AuthorityChangeReservation | None:
        """Atomically reserve a new operation or recover an exact semantic replay.

        A repeated key with a different semantic intent returns None. The
        original requested_at is retained across retries and restarts.
        """
        if not isinstance(intent, AuthorityChangeIntent):
            raise ContractError("intent debe ser AuthorityChangeIntent")
        canonical = _canonical_intent(intent)
        digest = hashlib.sha256(canonical).hexdigest()
        requested_at = _utc_text(intent.requested_at)
        now = _utc_text(datetime.now(timezone.utc))

        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            existing = connection.execute(
                """
                SELECT i.intent_digest, i.intent_canonical, i.operation_id
                FROM authority_change_idempotency AS i
                WHERE i.consumer_id = ? AND i.idempotency_key = ?
                """,
                (intent.consumer_id, intent.idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["intent_digest"] != digest
                    or bytes(existing["intent_canonical"]) != canonical
                ):
                    return None
                row = self._select_operation(
                    connection, existing["operation_id"]
                )
                return None if row is None else self._reservation(row)

            operation_id = uuid4().hex
            connection.execute(
                """
                INSERT INTO authority_change_operations (
                    operation_id, consumer_id, authority_kind, authority_id,
                    expected_revision, proposed_revision, change_kind,
                    request_context_ref, requested_at, status, created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, ?)
                """,
                (
                    operation_id,
                    intent.consumer_id,
                    intent.authority_kind.value,
                    intent.authority_id,
                    intent.expected_revision,
                    intent.proposed_revision,
                    intent.change_kind,
                    intent.request_context_ref,
                    requested_at,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO authority_change_idempotency (
                    consumer_id, idempotency_key, operation_id,
                    intent_digest, intent_canonical, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.consumer_id,
                    intent.idempotency_key,
                    operation_id,
                    digest,
                    canonical,
                    now,
                ),
            )
            row = self._select_operation(connection, operation_id)
            if row is None:
                raise sqlite3.DatabaseError(
                    "la reserva recién creada no pudo recuperarse"
                )
            return self._reservation(row)

    @staticmethod
    def _select_multi_operation(connection, operation_id: str):
        return connection.execute(
            """
            SELECT o.*, i.idempotency_key
            FROM multi_authority_change_operations AS o
            JOIN multi_authority_change_idempotency AS i
              ON i.operation_id = o.operation_id
            WHERE o.operation_id = ?
            """,
            (operation_id,),
        ).fetchone()

    @staticmethod
    def _multi_reservation(connection, row) -> MultiAuthorityChangeReservation:
        target_rows = connection.execute(
            """
            SELECT authority_kind, authority_id, expected_revision, proposed_revision
            FROM multi_authority_change_targets
            WHERE operation_id = ?
            ORDER BY authority_kind, authority_id
            """,
            (row["operation_id"],),
        ).fetchall()
        targets = tuple(
            AuthorityChangeTarget(
                authority_kind=AuthorityChangeTargetKind(target["authority_kind"]),
                authority_id=target["authority_id"],
                expected_revision=target["expected_revision"],
                proposed_revision=target["proposed_revision"],
            )
            for target in target_rows
        )
        intent = MultiAuthorityChangeIntent(
            idempotency_key=row["idempotency_key"],
            consumer_id=row["consumer_id"],
            action=row["action"],
            actor_identity_id=row["actor_identity_id"],
            owner_id=row["owner_id"],
            project_id=row["project_id"],
            environment_id=row["environment_id"],
            targets=targets,
            request_context_ref=row["request_context_ref"],
            requested_at=_parse_utc(row["requested_at"]),
        )
        return MultiAuthorityChangeReservation(
            operation_id=row["operation_id"],
            intent=intent,
            status=AuthorityChangeStatus(row["status"]),
        )

    def reserve_multi_change(
        self,
        intent: MultiAuthorityChangeIntent,
    ) -> MultiAuthorityChangeReservation | None:
        """Persist an exact multi-target intent and its target set atomically.

        This records durable operation identity and idempotency only. It does
        not yet acquire admission fences, authorize CAM, or mutate sources.
        """
        if not isinstance(intent, MultiAuthorityChangeIntent):
            raise ContractError("intent debe ser MultiAuthorityChangeIntent")
        canonical = _canonical_multi_intent(intent)
        digest = hashlib.sha256(canonical).hexdigest()
        requested_at = _utc_text(intent.requested_at)
        now = _utc_text(datetime.now(timezone.utc))

        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            existing = connection.execute(
                """
                SELECT intent_digest, intent_canonical, operation_id
                FROM multi_authority_change_idempotency
                WHERE consumer_id = ? AND idempotency_key = ?
                """,
                (intent.consumer_id, intent.idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["intent_digest"] != digest
                    or bytes(existing["intent_canonical"]) != canonical
                ):
                    return None
                row = self._select_multi_operation(
                    connection, existing["operation_id"]
                )
                return (
                    None if row is None
                    else self._multi_reservation(connection, row)
                )

            operation_id = uuid4().hex
            connection.execute(
                """
                INSERT INTO multi_authority_change_operations (
                    operation_id, consumer_id, action, actor_identity_id,
                    owner_id, project_id, environment_id, request_context_ref,
                    requested_at, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'REQUESTED', ?, ?)
                """,
                (
                    operation_id,
                    intent.consumer_id,
                    intent.action,
                    intent.actor_identity_id,
                    intent.owner_id,
                    intent.project_id,
                    intent.environment_id,
                    intent.request_context_ref,
                    requested_at,
                    now,
                    now,
                ),
            )
            for target in intent.targets:
                connection.execute(
                    """
                    INSERT INTO multi_authority_change_targets (
                        operation_id, authority_kind, authority_id,
                        expected_revision, proposed_revision
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        operation_id,
                        target.authority_kind.value,
                        target.authority_id,
                        target.expected_revision,
                        target.proposed_revision,
                    ),
                )
            connection.execute(
                """
                INSERT INTO multi_authority_change_idempotency (
                    consumer_id, idempotency_key, operation_id,
                    intent_digest, intent_canonical, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.consumer_id,
                    intent.idempotency_key,
                    operation_id,
                    digest,
                    canonical,
                    now,
                ),
            )
            row = self._select_multi_operation(connection, operation_id)
            if row is None:
                raise sqlite3.DatabaseError(
                    "la reserva multiobjetivo recién creada no pudo recuperarse"
                )
            return self._multi_reservation(connection, row)

    def acquire_multi_claims(self, operation_id: str) -> bool:
        """Atomically claim every target for a REQUESTED multi-authority operation.

        Returns False when another operation owns any target or the operation
        is absent/not claimable. Exact retries by the same operation return
        True. BEGIN IMMEDIATE serializes competing claim sets across SQLite
        connections sharing this database.
        
        Claims are deliberately not released by this store. A future
        consistency coordinator must provide durable terminal reconciliation
        evidence before a release protocol can safely exist.
        """
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")

        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            operation = connection.execute(
                """
                SELECT status FROM multi_authority_change_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if operation is None or operation["status"] != AuthorityChangeStatus.REQUESTED.value:
                return False

            targets = connection.execute(
                """
                SELECT authority_kind, authority_id
                FROM multi_authority_change_targets
                WHERE operation_id = ?
                ORDER BY authority_kind, authority_id
                """,
                (operation_id,),
            ).fetchall()
            if len(targets) < 2:
                raise sqlite3.DatabaseError(
                    "operación multiobjetivo sin conjunto completo de targets"
                )

            expected = {
                (row["authority_kind"], row["authority_id"])
                for row in targets
            }
            current_rows = connection.execute(
                """
                SELECT authority_kind, authority_id
                FROM multi_authority_change_claims
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchall()
            current = {
                (row["authority_kind"], row["authority_id"])
                for row in current_rows
            }
            if current:
                if current == expected:
                    return True
                raise sqlite3.DatabaseError(
                    "conjunto de claims parcial o inconsistente; requiere recuperación"
                )

            for authority_kind, authority_id in sorted(expected):
                conflict = connection.execute(
                    """
                    SELECT operation_id
                    FROM multi_authority_change_claims
                    WHERE authority_kind = ? AND authority_id = ?
                    """,
                    (authority_kind, authority_id),
                ).fetchone()
                if conflict is not None and conflict["operation_id"] != operation_id:
                    return False

            acquired_at = _utc_text(datetime.now(timezone.utc))
            for authority_kind, authority_id in sorted(expected):
                connection.execute(
                    """
                    INSERT INTO multi_authority_change_claims (
                        authority_kind, authority_id, operation_id, acquired_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (authority_kind, authority_id, operation_id, acquired_at),
                )
            claimed_count = connection.execute(
                """
                SELECT COUNT(*) FROM multi_authority_change_claims
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()[0]
            if claimed_count != len(expected):
                raise sqlite3.DatabaseError(
                    "adquisición de claims no produjo el conjunto completo"
                )
            return True


    @staticmethod
    def _terminal_evidence(connection, row) -> AuthorityChangeTerminalEvidence:
        target_rows = connection.execute(
            """
            SELECT authority_kind, authority_id, expected_revision,
                   proposed_revision, observed_revision
            FROM multi_authority_change_terminal_targets
            WHERE operation_id = ?
            ORDER BY authority_kind, authority_id
            """,
            (row["operation_id"],),
        ).fetchall()
        targets = tuple(
            AuthorityChangeTerminalTarget(
                authority_kind=AuthorityChangeTargetKind(target["authority_kind"]),
                authority_id=target["authority_id"],
                expected_revision=target["expected_revision"],
                proposed_revision=target["proposed_revision"],
                observed_revision=target["observed_revision"],
            )
            for target in target_rows
        )
        evidence = AuthorityChangeTerminalEvidence(
            evidence_id=row["evidence_id"],
            operation_id=row["operation_id"],
            outcome=AuthorityChangeTerminalOutcome(row["outcome"]),
            targets=targets,
            evidence_ref=row["evidence_ref"],
            recorded_by=row["recorded_by"],
            recorded_at=_parse_utc(row["recorded_at"]),
        )
        canonical = _canonical_terminal_evidence(evidence)
        if (
            hashlib.sha256(canonical).hexdigest() != row["evidence_digest"]
            or canonical != bytes(row["evidence_canonical"])
        ):
            raise sqlite3.DatabaseError(
                "la evidencia terminal persistida no supera la verificación de integridad"
            )
        return evidence

    def record_multi_terminal_evidence(
        self,
        evidence: AuthorityChangeTerminalEvidence,
    ) -> AuthorityChangeTerminalEvidence:
        """Persist a complete terminal receipt and status transition atomically.

        Only a RECONCILING operation with its complete exclusive claim set may
        be finalized. Exact retries recover the original receipt; a different
        receipt for the same operation is rejected. Claims are not released.
        """
        if not isinstance(evidence, AuthorityChangeTerminalEvidence):
            raise ContractError(
                "evidence debe ser AuthorityChangeTerminalEvidence"
            )
        canonical = _canonical_terminal_evidence(evidence)
        digest = hashlib.sha256(canonical).hexdigest()
        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            existing = connection.execute(
                """
                SELECT * FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (evidence.operation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["evidence_digest"] != digest
                    or bytes(existing["evidence_canonical"]) != canonical
                ):
                    raise ContractError(
                        "la operación ya tiene otra evidencia terminal inmutable"
                    )
                return self._terminal_evidence(connection, existing)

            operation = self._select_multi_operation(
                connection, evidence.operation_id
            )
            if operation is None:
                raise ContractError("operación multiobjetivo desconocida")
            reservation = self._multi_reservation(connection, operation)
            if reservation.status is not AuthorityChangeStatus.RECONCILING:
                raise ContractError(
                    "solo una operación RECONCILING puede finalizarse"
                )
            if not evidence.matches(reservation):
                raise ContractError(
                    "la evidencia no coincide exactamente con la reserva"
                )

            target_rows = connection.execute(
                """
                SELECT authority_kind, authority_id
                FROM multi_authority_change_targets
                WHERE operation_id = ?
                """,
                (evidence.operation_id,),
            ).fetchall()
            claimed_rows = connection.execute(
                """
                SELECT authority_kind, authority_id
                FROM multi_authority_change_claims
                WHERE operation_id = ?
                """,
                (evidence.operation_id,),
            ).fetchall()
            reserved_set = {
                (row["authority_kind"], row["authority_id"])
                for row in target_rows
            }
            claimed_set = {
                (row["authority_kind"], row["authority_id"])
                for row in claimed_rows
            }
            if len(reserved_set) < 2 or claimed_set != reserved_set:
                raise ContractError(
                    "la operación no conserva el conjunto completo de claims"
                )

            connection.execute(
                """
                INSERT INTO multi_authority_change_terminal_evidence (
                    operation_id, evidence_id, outcome, evidence_ref,
                    recorded_by, recorded_at, evidence_digest,
                    evidence_canonical
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.operation_id,
                    evidence.evidence_id,
                    evidence.outcome.value,
                    evidence.evidence_ref,
                    evidence.recorded_by,
                    _utc_text(evidence.recorded_at),
                    digest,
                    canonical,
                ),
            )
            for target in evidence.targets:
                connection.execute(
                    """
                    INSERT INTO multi_authority_change_terminal_targets (
                        operation_id, authority_kind, authority_id,
                        expected_revision, proposed_revision, observed_revision
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence.operation_id,
                        target.authority_kind.value,
                        target.authority_id,
                        target.expected_revision,
                        target.proposed_revision,
                        target.observed_revision,
                    ),
                )
            now = _utc_text(datetime.now(timezone.utc))
            updated = connection.execute(
                """
                UPDATE multi_authority_change_operations
                SET status = ?, updated_at = ?
                WHERE operation_id = ? AND status = 'RECONCILING'
                """,
                (evidence.outcome.value, now, evidence.operation_id),
            )
            if updated.rowcount != 1:
                raise sqlite3.DatabaseError(
                    "la transición terminal no pudo confirmarse"
                )
            stored = connection.execute(
                """
                SELECT * FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (evidence.operation_id,),
            ).fetchone()
            if stored is None:
                raise sqlite3.DatabaseError(
                    "el recibo terminal recién persistido no pudo recuperarse"
                )
            return self._terminal_evidence(connection, stored)

    def get_multi_terminal_evidence(
        self,
        operation_id: str,
    ) -> AuthorityChangeTerminalEvidence | None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            return (
                None if row is None
                else self._terminal_evidence(connection, row)
            )


    def release_multi_claims(self, operation_id: str) -> bool:
        """Release a complete claim set only after validating durable terminal evidence.

        The immutable release receipt and deletion of every claim are committed
        in one SQLite UoW. Exact retries return True; absent/non-terminal
        operations return False. Corrupt or partial state fails closed.
        """
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")

        with self._database.unit_of_work() as unit:
            connection = unit._connection_for(self._database)
            operation = self._select_multi_operation(connection, operation_id)
            if operation is None:
                return False
            status = AuthorityChangeStatus(operation["status"])
            if status not in (
                AuthorityChangeStatus.COMPLETED,
                AuthorityChangeStatus.ABORTED,
            ):
                return False

            receipt = connection.execute(
                """
                SELECT * FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if receipt is None:
                raise sqlite3.DatabaseError(
                    "operación terminal sin recibo durable"
                )
            evidence = self._terminal_evidence(connection, receipt)
            if evidence.outcome.value != status.value:
                raise sqlite3.DatabaseError(
                    "estado terminal y recibo no coinciden"
                )

            targets = connection.execute(
                """
                SELECT authority_kind, authority_id, expected_revision,
                       proposed_revision
                FROM multi_authority_change_targets
                WHERE operation_id = ?
                ORDER BY authority_kind, authority_id
                """,
                (operation_id,),
            ).fetchall()
            terminal_targets = connection.execute(
                """
                SELECT authority_kind, authority_id, expected_revision,
                       proposed_revision, observed_revision
                FROM multi_authority_change_terminal_targets
                WHERE operation_id = ?
                ORDER BY authority_kind, authority_id
                """,
                (operation_id,),
            ).fetchall()
            claims = connection.execute(
                """
                SELECT authority_kind, authority_id
                FROM multi_authority_change_claims
                WHERE operation_id = ?
                ORDER BY authority_kind, authority_id
                """,
                (operation_id,),
            ).fetchall()
            reserved_set = {
                (row["authority_kind"], row["authority_id"],
                 row["expected_revision"], row["proposed_revision"])
                for row in targets
            }
            evidence_set = {
                (row["authority_kind"], row["authority_id"],
                 row["expected_revision"], row["proposed_revision"])
                for row in terminal_targets
            }
            claim_set = {
                (row["authority_kind"], row["authority_id"])
                for row in claims
            }
            expected_claims = {
                (row["authority_kind"], row["authority_id"])
                for row in targets
            }
            if (
                len(reserved_set) < 2
                or evidence_set != reserved_set
                or evidence.targets != tuple(
                    AuthorityChangeTerminalTarget(
                        authority_kind=AuthorityChangeTargetKind(row["authority_kind"]),
                        authority_id=row["authority_id"],
                        expected_revision=row["expected_revision"],
                        proposed_revision=row["proposed_revision"],
                        observed_revision=row["observed_revision"],
                    )
                    for row in terminal_targets
                )
            ):
                raise sqlite3.DatabaseError(
                    "evidencia terminal incompleta o inconsistente"
                )

            existing_release = connection.execute(
                """
                SELECT evidence_digest FROM multi_authority_change_claim_releases
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if existing_release is not None:
                if existing_release["evidence_digest"] != receipt["evidence_digest"]:
                    raise sqlite3.DatabaseError(
                        "el recibo de liberación no coincide con la evidencia terminal"
                    )
                if claims:
                    raise sqlite3.DatabaseError(
                        "liberación registrada pero quedan claims activos"
                    )
                return True

            if (
                claim_set != expected_claims
                or len(claims) != len(targets)
            ):
                raise sqlite3.DatabaseError(
                    "conjunto de claims incompleto o inconsistente"
                )

            connection.execute(
                """
                INSERT INTO multi_authority_change_claim_releases (
                    operation_id, evidence_digest, released_at
                ) VALUES (?, ?, ?)
                """,
                (
                    operation_id,
                    receipt["evidence_digest"],
                    _utc_text(datetime.now(timezone.utc)),
                ),
            )
            deleted = connection.execute(
                """
                DELETE FROM multi_authority_change_claims
                WHERE operation_id = ?
                """,
                (operation_id,),
            )
            if deleted.rowcount != len(targets):
                raise sqlite3.DatabaseError(
                    "no se liberó el conjunto completo de claims"
                )
            remaining = connection.execute(
                """
                SELECT COUNT(*) FROM multi_authority_change_claims
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()[0]
            if remaining != 0:
                raise sqlite3.DatabaseError(
                    "quedaron claims activos después de la liberación"
                )
            return True


    def audit_multi_claims(
        self,
        operation_id: str,
    ) -> MultiAuthorityClaimAudit | None:
        """Return a read-only consistency classification for one durable operation.

        This method never repairs state, releases claims, or treats a digest as
        proof that external reconciliation actually occurred.
        """
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            operation = self._select_multi_operation(connection, operation_id)
            if operation is None:
                return None
            reservation = self._multi_reservation(connection, operation)
            targets_rows = connection.execute(
                """
                SELECT authority_kind, authority_id, expected_revision,
                       proposed_revision
                FROM multi_authority_change_targets
                WHERE operation_id = ?
                ORDER BY authority_kind, authority_id
                """,
                (operation_id,),
            ).fetchall()
            claims_rows = connection.execute(
                """
                SELECT authority_kind, authority_id
                FROM multi_authority_change_claims
                WHERE operation_id = ?
                ORDER BY authority_kind, authority_id
                """,
                (operation_id,),
            ).fetchall()
            evidence_row = connection.execute(
                """
                SELECT * FROM multi_authority_change_terminal_evidence
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            release_row = connection.execute(
                """
                SELECT evidence_digest FROM multi_authority_change_claim_releases
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()

            reserved = tuple(
                AuthorityChangeTarget(
                    authority_kind=AuthorityChangeTargetKind(row["authority_kind"]),
                    authority_id=row["authority_id"],
                    expected_revision=row["expected_revision"],
                    proposed_revision=row["proposed_revision"],
                )
                for row in targets_rows
            )
            reserved_by_identity = {
                (item.authority_kind, item.authority_id): item
                for item in reserved
            }
            claimed = tuple(
                reserved_by_identity[
                    (AuthorityChangeTargetKind(row["authority_kind"]), row["authority_id"])
                ]
                for row in claims_rows
                if (
                    AuthorityChangeTargetKind(row["authority_kind"]),
                    row["authority_id"],
                ) in reserved_by_identity
            )
            exact_claim_set = (
                len(claims_rows) == len(targets_rows)
                and len(claimed) == len(reserved)
                and {
                    (row["authority_kind"], row["authority_id"])
                    for row in claims_rows
                } == {
                    (item.authority_kind.value, item.authority_id)
                    for item in reserved
                }
            )

            evidence = None
            evidence_valid = False
            if evidence_row is not None:
                try:
                    evidence = self._terminal_evidence(connection, evidence_row)
                    evidence_valid = (
                        evidence.matches(reservation)
                        and evidence.outcome.value == reservation.status.value
                    )
                except (ContractError, sqlite3.DatabaseError, ValueError, KeyError):
                    evidence = None
                    evidence_valid = False

            status = reservation.status
            if len(reserved) < 2:
                classification = MultiAuthorityClaimAuditStatus.INCONSISTENT
            elif release_row is not None:
                if (
                    evidence_valid
                    and release_row["evidence_digest"] == evidence_row["evidence_digest"]
                    and not claims_rows
                    and status in (
                        AuthorityChangeStatus.COMPLETED,
                        AuthorityChangeStatus.ABORTED,
                    )
                ):
                    classification = MultiAuthorityClaimAuditStatus.RELEASED
                else:
                    classification = MultiAuthorityClaimAuditStatus.INCONSISTENT
            elif status in (
                AuthorityChangeStatus.COMPLETED,
                AuthorityChangeStatus.ABORTED,
            ):
                if evidence_valid and exact_claim_set:
                    classification = (
                        MultiAuthorityClaimAuditStatus.TERMINAL_CLAIMS_HELD
                    )
                else:
                    classification = MultiAuthorityClaimAuditStatus.INCONSISTENT
            elif evidence_row is not None:
                classification = MultiAuthorityClaimAuditStatus.INCONSISTENT
            elif not claims_rows:
                classification = MultiAuthorityClaimAuditStatus.UNCLAIMED
            elif exact_claim_set:
                classification = MultiAuthorityClaimAuditStatus.CLAIMED
            else:
                classification = MultiAuthorityClaimAuditStatus.INCONSISTENT

            return MultiAuthorityClaimAudit(
                operation_id=operation_id,
                operation_status=status,
                audit_status=classification,
                reserved_targets=reserved,
                claimed_targets=claimed,
                terminal_evidence=evidence,
                release_digest=(
                    None if release_row is None else release_row["evidence_digest"]
                ),
            )

    def get_multi_claims(self, operation_id: str) -> tuple[AuthorityChangeTarget, ...]:
        """Return the immutable target claims currently held by an operation."""
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT t.authority_kind, t.authority_id,
                       t.expected_revision, t.proposed_revision
                FROM multi_authority_change_claims AS c
                JOIN multi_authority_change_targets AS t
                  ON t.operation_id = c.operation_id
                 AND t.authority_kind = c.authority_kind
                 AND t.authority_id = c.authority_id
                WHERE c.operation_id = ?
                ORDER BY t.authority_kind, t.authority_id
                """,
                (operation_id,),
            ).fetchall()
        return tuple(
            AuthorityChangeTarget(
                authority_kind=AuthorityChangeTargetKind(row["authority_kind"]),
                authority_id=row["authority_id"],
                expected_revision=row["expected_revision"],
                proposed_revision=row["proposed_revision"],
            )
            for row in rows
        )

    def get_multi_reservation(
        self,
        operation_id: str,
    ) -> MultiAuthorityChangeReservation | None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            row = self._select_multi_operation(connection, operation_id)
            return (
                None if row is None
                else self._multi_reservation(connection, row)
            )

    def get_multi_by_idempotency_key(
        self,
        consumer_id: str,
        idempotency_key: str,
    ) -> MultiAuthorityChangeReservation | None:
        if (
            not isinstance(consumer_id, str) or not consumer_id.strip()
            or not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise ContractError("consumer_id e idempotency_key son obligatorios")
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT o.*, i.idempotency_key
                FROM multi_authority_change_operations AS o
                JOIN multi_authority_change_idempotency AS i
                  ON i.operation_id = o.operation_id
                WHERE i.consumer_id = ? AND i.idempotency_key = ?
                """,
                (consumer_id, idempotency_key),
            ).fetchone()
            return (
                None if row is None
                else self._multi_reservation(connection, row)
            )

    def get_by_idempotency_key(
        self,
        consumer_id: str,
        idempotency_key: str,
    ) -> AuthorityChangeResult | None:
        if (
            not isinstance(consumer_id, str) or not consumer_id.strip()
            or not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise ContractError("consumer_id e idempotency_key son obligatorios")
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT o.*
                FROM authority_change_operations AS o
                JOIN authority_change_idempotency AS i
                  ON i.operation_id = o.operation_id
                WHERE i.consumer_id = ? AND i.idempotency_key = ?
                """,
                (consumer_id, idempotency_key),
            ).fetchone()
            return None if row is None else self._result(row)

    def get_result(self, operation_id: str) -> AuthorityChangeResult | None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM authority_change_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            return None if row is None else self._result(row)

    def get_reservation(
        self,
        operation_id: str,
    ) -> AuthorityChangeReservation | None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ContractError("operation_id debe ser una cadena no vacía")
        with self._database.connection() as connection:
            row = self._select_operation(connection, operation_id)
            return None if row is None else self._reservation(row)
