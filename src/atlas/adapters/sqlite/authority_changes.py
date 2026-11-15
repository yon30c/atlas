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
