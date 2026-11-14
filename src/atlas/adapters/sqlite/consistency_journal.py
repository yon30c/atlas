"""Transactional SQLite implementation of K01 append, resolution and diagnostics.

Structural recovery reads are diagnostic only. Operational recovery must pass
through the independent local recovery verifier before reducer access.
"""
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind, AuthorityRevision, AuthorizationRevisionSet, ReadAdmissionStatus,
)
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.journal import (
    ConsistencyPosition, ConsistencyRecordKind, ConsistencyTransition,
    JournalCommit, JournalEntry, JournalOperationResolution,
    JournalOperationResolutionStatus, ConsistencyRecoveryState, ConsistencyCheckpoint,
    ConsistencyRecoveryLoadResult, ConsistencyRecoveryLoadStatus,
    consistency_transition_request_projection,
)
from atlas.memory.local_auth import (
    CANONICALIZATION_VERSION, ENVELOPE_VERSION, canonical_json_bytes,
    checkpoint_payload, journal_entry_payload, object_commitment,
)
from atlas.memory.models import MemoryScopeKind
from atlas.ports.local_consistency_signer import LocalConsistencySignerPort
from atlas.memory.local_recovery_verifier import LocalConsistencyRecoveryVerifier
from atlas.memory.local_trust_policy import LocalConsistencyTrustPolicy
from atlas.memory.trust import (
    ConsistencyRecoveryTrustContext,
    ConsistencyRecoveryVerificationResult,
    ConsistencyRecoveryVerificationStatus,
)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ContractError("datetime debe estar en UTC")
    return value.isoformat(timespec="microseconds")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractError("timestamp persistido no está en UTC")
    return parsed


def _transition_from_bytes(raw: bytes) -> ConsistencyTransition:
    try:
        data = json.loads(raw.decode("utf-8"))
        data["occurred_at"] = _parse_datetime(data["occurred_at"])
        data["record_kind"] = ConsistencyRecordKind(data["record_kind"])
        if data.get("scope_kind") is not None:
            data["scope_kind"] = MemoryScopeKind(data["scope_kind"])
        if data.get("authority_kind") is not None:
            data["authority_kind"] = AuthorityKind(data["authority_kind"])
        if data.get("admission_terminal_status") is not None:
            data["admission_terminal_status"] = ReadAdmissionStatus(
                data["admission_terminal_status"]
            )
        for name in ("route_ids", "affected_admission_ids"):
            data[name] = frozenset(data.get(name, ()))
        revisions = data.get("revisions")
        if revisions is not None:
            for name in (
                "memory_revision", "version_revision", "identity_revision",
                "project_revision", "environment_revision", "grant_revision",
            ):
                item = revisions.get(name)
                if item is not None:
                    item["authority_kind"] = AuthorityKind(item["authority_kind"])
                    revisions[name] = AuthorityRevision(**item)
            data["revisions"] = AuthorizationRevisionSet(**revisions)
        return ConsistencyTransition(**data)
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise ContractError("transición SQLite no se puede reconstruir") from exc


class SQLiteConsistencyJournal:
    """Single-host K01 journal with explicitly gated local recovery reads."""

    def __init__(
        self,
        database: SQLiteDatabase,
        signer: LocalConsistencySignerPort,
        *,
        reducer_version: str,
        issuer_id: str,
        issuer_role: str,
        key_reference: str,
        trust_policy_version: str,
        recovery_verifier: LocalConsistencyRecoveryVerifier | None = None,
        recovery_trust_policy: LocalConsistencyTrustPolicy | None = None,
    ) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        if signer is None or not callable(getattr(signer, "sign_envelope", None)):
            raise ContractError("signer debe implementar sign_envelope")
        for name, value in (
            ("reducer_version", reducer_version), ("issuer_id", issuer_id),
            ("issuer_role", issuer_role), ("key_reference", key_reference),
            ("trust_policy_version", trust_policy_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{name} debe ser una cadena no vacía")
        self._database = database
        self._signer = signer
        self._reducer_version = reducer_version
        self._issuer_id = issuer_id
        self._issuer_role = issuer_role
        self._key_reference = key_reference
        if (recovery_verifier is None) != (recovery_trust_policy is None):
            raise ContractError("recovery_verifier y recovery_trust_policy deben configurarse juntos")
        if recovery_verifier is not None and (
            not isinstance(recovery_verifier, LocalConsistencyRecoveryVerifier)
            or not isinstance(recovery_trust_policy, LocalConsistencyTrustPolicy)
            or recovery_verifier.trust_policy is not recovery_trust_policy
            or recovery_trust_policy.policy_version != trust_policy_version
        ):
            raise ContractError("composición de recuperación local no coincide con la política del journal")
        self._trust_policy_version = trust_policy_version
        self._recovery_verifier = recovery_verifier
        self._recovery_trust_policy = recovery_trust_policy

    def create_local_domain(self, domain_id: str, authority_epoch: int) -> bool:
        """Explicit one-time domain bootstrap; never silently changes an existing domain."""
        if not isinstance(domain_id, str) or not domain_id.strip():
            raise ContractError("domain_id debe ser no vacío")
        if isinstance(authority_epoch, bool) or not isinstance(authority_epoch, int) or authority_epoch < 1:
            raise ContractError("authority_epoch debe ser positivo")
        now = _utc_text(datetime.now(timezone.utc))
        try:
            with self._database.write_transaction() as connection:
                existing = connection.execute(
                    "SELECT authority_epoch, profile, trust_policy_version "
                    "FROM consistency_domains WHERE domain_id = ?", (domain_id,)
                ).fetchone()
                if existing is not None:
                    return (
                        existing["authority_epoch"] == authority_epoch
                        and existing["profile"] == "local"
                        and existing["trust_policy_version"] == self._trust_policy_version
                    )
                connection.execute(
                    """
                    INSERT INTO consistency_domains (
                        domain_id, authority_epoch, head_sequence, head_commitment,
                        profile, trust_policy_version, created_at, updated_at
                    ) VALUES (?, ?, 0, NULL, 'local', ?, ?, ?)
                    """,
                    (domain_id, authority_epoch, self._trust_policy_version, now, now),
                )
            return True
        except sqlite3.Error:
            return False

    @staticmethod
    def _position(domain_id: str, epoch: int, sequence: int) -> ConsistencyPosition:
        return ConsistencyPosition(domain_id, epoch, sequence)

    @staticmethod
    def _row_commit(row: sqlite3.Row, *, replayed: bool) -> JournalCommit:
        return JournalCommit(
            ConsistencyPosition(row["domain_id"], row["authority_epoch"], row["sequence"]),
            row["record_id"],
            replayed,
        )

    def _load_append(
        self, connection: sqlite3.Connection, domain_id: str, epoch: int,
        *, append_id: str | None = None, idempotency_key: str | None = None,
    ) -> sqlite3.Row | None:
        if (append_id is None) == (idempotency_key is None):
            raise ContractError("se requiere exactamente un localizador")
        predicate = "o.append_id=?" if append_id is not None else "o.idempotency_key=?"
        locator = append_id if append_id is not None else idempotency_key
        return connection.execute(
            f"""
            SELECT o.*, j.transition_canonical, j.record_kind, j.schema_version,
                   j.envelope_version, j.reducer_version, j.previous_commitment,
                   j.object_commitment, j.issuer_id, j.issuer_role, j.key_reference,
                   j.trust_policy_version, j.issued_at, j.authentication_evidence
            FROM journal_operations o
            JOIN journal_entries j
              ON j.domain_id=o.domain_id AND j.authority_epoch=o.authority_epoch
             AND j.sequence=o.sequence AND j.record_id=o.record_id
             AND j.operation_id=o.operation_id
            WHERE o.domain_id=? AND o.authority_epoch=? AND {predicate}
            """,
            (domain_id, epoch, locator),
        ).fetchone()

    @staticmethod
    def _request_bytes(domain_id: str, epoch: int, transition: ConsistencyTransition) -> bytes:
        return canonical_json_bytes(
            consistency_transition_request_projection(domain_id, epoch, transition)
        )

    def append_transition(
        self,
        expected_position: ConsistencyPosition,
        append_id: str,
        transition: ConsistencyTransition,
    ) -> JournalCommit | None:
        if (
            not isinstance(expected_position, ConsistencyPosition)
            or not isinstance(append_id, str) or not append_id.strip()
            or not isinstance(transition, ConsistencyTransition)
        ):
            return None
        domain_id = expected_position.consistency_domain_id
        epoch = expected_position.authority_epoch
        request_bytes = self._request_bytes(domain_id, epoch, transition)
        request_digest = hashlib.sha256(request_bytes).hexdigest()
        now = _utc_text(datetime.now(timezone.utc))
        try:
            with self._database.write_transaction() as connection:
                domain = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?", (domain_id,)
                ).fetchone()
                if (
                    domain is None or domain["authority_epoch"] != epoch
                    or domain["profile"] != "local"
                    or domain["trust_policy_version"] != self._trust_policy_version
                ):
                    return None

                by_key = (
                    self._load_append(
                        connection, domain_id, epoch,
                        idempotency_key=transition.idempotency_key,
                    )
                    if transition.idempotency_key is not None else None
                )
                by_append = self._load_append(
                    connection, domain_id, epoch, append_id=append_id
                )
                if by_key is not None and by_append is not None and (
                    (by_key["sequence"], by_key["record_id"])
                    != (by_append["sequence"], by_append["record_id"])
                ):
                    return None
                existing = by_key or by_append
                if existing is not None:
                    if (
                        bytes(existing["request_canonical"]) != request_bytes
                        or existing["idempotency_key"] != transition.idempotency_key
                        or (by_append is not None and by_append["append_id"] != append_id)
                    ):
                        return None
                    return self._row_commit(existing, replayed=True)

                if expected_position.sequence != domain["head_sequence"]:
                    return None
                if transition.record_id == "" or transition.operation_id == "":
                    return None

                sequence = domain["head_sequence"] + 1
                position = self._position(domain_id, epoch, sequence)
                unsigned = AuthenticatedConsistencyEnvelope(
                    object_kind="journal_entry",
                    envelope_version=ENVELOPE_VERSION,
                    consistency_domain_id=domain_id,
                    authority_epoch=epoch,
                    sequence=sequence,
                    object_id=transition.record_id,
                    schema_version=transition.schema_version,
                    reducer_version=self._reducer_version,
                    previous_commitment=domain["head_commitment"],
                    object_commitment="pending",
                    issuer_id=self._issuer_id,
                    issuer_role=self._issuer_role,
                    key_reference=self._key_reference,
                    trust_policy_version=self._trust_policy_version,
                    issued_at=datetime.now(timezone.utc),
                    authentication_evidence="pending",
                )
                unsigned_entry = JournalEntry(position, transition)
                signed = self._signer.sign_envelope(
                    unsigned, journal_entry_payload(unsigned_entry)
                )
                if not isinstance(signed, AuthenticatedConsistencyEnvelope):
                    return None
                expected_commitment = object_commitment(journal_entry_payload(unsigned_entry))
                if (
                    signed.object_kind != unsigned.object_kind
                    or signed.envelope_version != unsigned.envelope_version
                    or signed.consistency_domain_id != domain_id
                    or signed.authority_epoch != epoch
                    or signed.sequence != sequence
                    or signed.object_id != transition.record_id
                    or signed.schema_version != transition.schema_version
                    or signed.reducer_version != self._reducer_version
                    or signed.previous_commitment != domain["head_commitment"]
                    or signed.issuer_id != self._issuer_id
                    or signed.issuer_role != self._issuer_role
                    or signed.key_reference != self._key_reference
                    or signed.trust_policy_version != self._trust_policy_version
                    or signed.issued_at != unsigned.issued_at
                    or signed.object_commitment != expected_commitment
                    or not signed.authentication_evidence
                ):
                    return None
                entry = JournalEntry(position, transition, signed)
                transition_bytes = canonical_json_bytes(transition)
                connection.execute(
                    """
                    INSERT INTO journal_entries (
                        domain_id, authority_epoch, sequence, record_id, operation_id,
                        record_kind, schema_version, transition_canonical,
                        envelope_version, reducer_version, previous_commitment,
                        object_commitment, issuer_id, issuer_role, key_reference,
                        trust_policy_version, issued_at, authentication_evidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        domain_id, epoch, sequence, transition.record_id,
                        transition.operation_id, transition.record_kind.value,
                        transition.schema_version, transition_bytes,
                        signed.envelope_version, signed.reducer_version,
                        signed.previous_commitment, signed.object_commitment,
                        signed.issuer_id, signed.issuer_role, signed.key_reference,
                        signed.trust_policy_version, _utc_text(signed.issued_at),
                        signed.authentication_evidence,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO journal_operations (
                        domain_id, authority_epoch, append_id, operation_id, idempotency_key,
                        request_canonical, request_digest, sequence, record_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        domain_id, epoch, append_id, transition.operation_id,
                        transition.idempotency_key, request_bytes, request_digest,
                        sequence, transition.record_id, now,
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE consistency_domains
                    SET head_sequence=?, head_commitment=?, updated_at=?
                    WHERE domain_id=? AND authority_epoch=? AND head_sequence=?
                    """,
                    (
                        sequence, signed.object_commitment, now, domain_id, epoch,
                        expected_position.sequence,
                    ),
                )
                if updated.rowcount != 1:
                    raise sqlite3.IntegrityError("head CAS failed; append transaction rolled back")
            return JournalCommit(position, transition.record_id, False)
        except Exception:
            # The signer port defines failure by exception, not by a closed
            # exception taxonomy. Any ordinary failure aborts the transaction.
            return None

    def resolve_append(
        self,
        domain_id: str,
        authority_epoch: int,
        append_id: str,
        idempotency_key: str | None,
        expected_transition: ConsistencyTransition,
        expected_position: ConsistencyPosition,
    ) -> JournalOperationResolution:
        unknown = JournalOperationResolutionStatus.UNKNOWN
        if (
            not isinstance(append_id, str) or not append_id.strip()
            or not isinstance(expected_transition, ConsistencyTransition)
            or not isinstance(expected_position, ConsistencyPosition)
            or expected_transition.idempotency_key != idempotency_key
            or expected_position.consistency_domain_id != domain_id
            or expected_position.authority_epoch != authority_epoch
        ):
            return JournalOperationResolution(
                unknown, append_id if isinstance(append_id, str) else "",
                idempotency_key, expected_position, expected_transition, None, None,
            )
        try:
            with self._database.connection() as connection:
                domain = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?", (domain_id,)
                ).fetchone()
                if (
                    domain is None or domain["authority_epoch"] != authority_epoch
                    or domain["profile"] != "local"
                    or domain["trust_policy_version"] != self._trust_policy_version
                ):
                    raise sqlite3.DatabaseError("dominio no verificable")
                by_append = self._load_append(
                    connection, domain_id, authority_epoch, append_id=append_id
                )
                by_key = (
                    self._load_append(
                        connection, domain_id, authority_epoch,
                        idempotency_key=idempotency_key,
                    )
                    if idempotency_key is not None else None
                )
                current = self._position(domain_id, authority_epoch, domain["head_sequence"])
                if by_append is not None and by_key is not None and (
                    (by_append["sequence"], by_append["record_id"])
                    != (by_key["sequence"], by_key["record_id"])
                ):
                    return JournalOperationResolution(
                        JournalOperationResolutionStatus.CONFLICT,
                        append_id, idempotency_key, expected_position,
                        expected_transition, current, None,
                    )
                row = by_key or by_append
                if row is None:
                    if current.sequence < expected_position.sequence:
                        raise sqlite3.DatabaseError("posición actual regresiva")
                    return JournalOperationResolution(
                        JournalOperationResolutionStatus.NOT_COMMITTED,
                        append_id, idempotency_key, expected_position,
                        expected_transition, current, None,
                    )
                committed = _transition_from_bytes(bytes(row["transition_canonical"]))
                request_bytes = self._request_bytes(
                    domain_id, authority_epoch, expected_transition
                )
                if (
                    bytes(row["request_canonical"]) != request_bytes
                    or row["idempotency_key"] != idempotency_key
                    or (by_append is not None and row["append_id"] != append_id)
                ):
                    return JournalOperationResolution(
                        JournalOperationResolutionStatus.CONFLICT,
                        append_id, idempotency_key, expected_position,
                        expected_transition, current, None,
                    )
                commit = self._row_commit(row, replayed=True)
                return JournalOperationResolution(
                    JournalOperationResolutionStatus.COMMITTED_EXACT,
                    append_id, idempotency_key, expected_position,
                    expected_transition, current, commit, committed,
                )
        except Exception:
            return JournalOperationResolution(
                unknown, append_id, idempotency_key, expected_position,
                expected_transition, None, None,
            )


    @staticmethod
    def _envelope_from_row(row: sqlite3.Row, *, object_kind: str, object_id: str,
                           domain_id: str, epoch: int, sequence: int,
                           schema_version: int) -> AuthenticatedConsistencyEnvelope:
        return AuthenticatedConsistencyEnvelope(
            object_kind=object_kind,
            envelope_version=row["envelope_version"],
            consistency_domain_id=domain_id,
            authority_epoch=epoch,
            sequence=sequence,
            object_id=object_id,
            schema_version=schema_version,
            reducer_version=row["reducer_version"],
            previous_commitment=row["previous_commitment"],
            object_commitment=row["object_commitment"],
            issuer_id=row["issuer_id"],
            issuer_role=row["issuer_role"],
            key_reference=row["key_reference"],
            trust_policy_version=row["trust_policy_version"],
            issued_at=_parse_datetime(row["issued_at"]),
            authentication_evidence=row["authentication_evidence"],
        )

    @staticmethod
    def _checkpoint_from_row(
        row: sqlite3.Row, *, domain_id: str, epoch: int,
    ) -> ConsistencyCheckpoint:
        checkpoint_id = row["checkpoint_id"]
        sequence = row["sequence"]
        envelope = SQLiteConsistencyJournal._envelope_from_row(
            row,
            object_kind="checkpoint",
            object_id=checkpoint_id,
            domain_id=domain_id,
            epoch=epoch,
            sequence=sequence,
            schema_version=row["schema_version"],
        )
        return ConsistencyCheckpoint(
            checkpoint_id=checkpoint_id,
            position=ConsistencyPosition(domain_id, epoch, sequence),
            state_reference=row["state_reference"],
            integrity_reference=row["integrity_reference"],
            created_at=_parse_datetime(row["created_at"]),
            envelope=envelope,
        )

    def load_recovery_state_result(
        self, domain_id: str,
    ) -> ConsistencyRecoveryLoadResult:
        """Load one consistent journal suffix and its latest structural checkpoint."""
        rejected = ConsistencyRecoveryLoadResult(ConsistencyRecoveryLoadStatus.REJECTED)
        unavailable = ConsistencyRecoveryLoadResult(ConsistencyRecoveryLoadStatus.UNAVAILABLE)
        if not isinstance(domain_id, str) or not domain_id.strip():
            return rejected
        try:
            with self._database.connection() as connection:
                connection.execute("BEGIN")
                domain = connection.execute(
                    "SELECT * FROM consistency_domains WHERE domain_id=?",
                    (domain_id,),
                ).fetchone()
                if domain is None:
                    return unavailable
                if (
                    domain["profile"] != "local"
                    or domain["trust_policy_version"] != self._trust_policy_version
                ):
                    return rejected

                epoch = domain["authority_epoch"]
                head = domain["head_sequence"]
                if (
                    isinstance(head, bool) or not isinstance(head, int) or head < 0
                ):
                    return rejected

                checkpoint_rows = connection.execute(
                    """
                    SELECT * FROM checkpoints
                    WHERE domain_id=? AND authority_epoch=?
                    ORDER BY sequence DESC
                    """,
                    (domain_id, epoch),
                ).fetchall()
                if head == 0:
                    if checkpoint_rows or domain["head_commitment"] is not None:
                        return rejected
                    return unavailable
                if (
                    not isinstance(domain["head_commitment"], str)
                    or not domain["head_commitment"]
                ):
                    return rejected
                if any(
                    isinstance(row["sequence"], bool)
                    or not isinstance(row["sequence"], int)
                    or row["sequence"] < 0
                    or row["sequence"] >= head
                    for row in checkpoint_rows
                ):
                    return rejected

                checkpoint = None
                checkpoint_sequence = 0
                previous_commitment = None
                if checkpoint_rows:
                    checkpoint = self._checkpoint_from_row(
                        checkpoint_rows[0], domain_id=domain_id, epoch=epoch
                    )
                    checkpoint_sequence = checkpoint.position.sequence
                    if (
                        checkpoint.envelope is None
                        or checkpoint.envelope.previous_commitment is not None
                        or object_commitment(checkpoint_payload(checkpoint))
                            != checkpoint.envelope.object_commitment
                    ):
                        return rejected
                    previous_commitment = checkpoint.envelope.object_commitment

                rows = connection.execute(
                    """
                    SELECT * FROM journal_entries
                    WHERE domain_id=? AND authority_epoch=? AND sequence>?
                    ORDER BY sequence ASC
                    """,
                    (domain_id, epoch, checkpoint_sequence),
                ).fetchall()
                operation_rows = connection.execute(
                    """
                    SELECT * FROM journal_operations
                    WHERE domain_id=? AND authority_epoch=? AND sequence>?
                    ORDER BY sequence ASC
                    """,
                    (domain_id, epoch, checkpoint_sequence),
                ).fetchall()

                expected_count = head - checkpoint_sequence
                if len(rows) != expected_count or len(operation_rows) != expected_count:
                    return rejected

                unmatched = connection.execute(
                    """
                    SELECT j.sequence
                    FROM journal_entries j
                    LEFT JOIN journal_operations o
                      ON o.domain_id=j.domain_id
                     AND o.authority_epoch=j.authority_epoch
                     AND o.sequence=j.sequence
                     AND o.record_id=j.record_id
                     AND o.operation_id=j.operation_id
                    WHERE j.domain_id=? AND j.authority_epoch=? AND j.sequence>?
                    GROUP BY j.sequence
                    HAVING COUNT(o.append_id) != 1
                    LIMIT 1
                    """,
                    (domain_id, epoch, checkpoint_sequence),
                ).fetchone()
                if unmatched is not None:
                    return rejected

                entries = []
                expected_sequence = checkpoint_sequence + 1
                for row, operation in zip(rows, operation_rows, strict=True):
                    sequence = row["sequence"]
                    if (
                        operation["sequence"] != sequence
                        or operation["record_id"] != row["record_id"]
                        or operation["operation_id"] != row["operation_id"]
                        or sequence != expected_sequence
                    ):
                        return rejected
                    raw_transition = bytes(row["transition_canonical"])
                    transition = _transition_from_bytes(raw_transition)
                    if canonical_json_bytes(transition) != raw_transition:
                        return rejected
                    expected_request = self._request_bytes(domain_id, epoch, transition)
                    if (
                        bytes(operation["request_canonical"]) != expected_request
                        or operation["request_digest"] != hashlib.sha256(
                            expected_request
                        ).hexdigest()
                        or operation["idempotency_key"] != transition.idempotency_key
                    ):
                        return rejected
                    if (
                        row["record_id"] != transition.record_id
                        or row["operation_id"] != transition.operation_id
                        or row["record_kind"] != transition.record_kind.value
                        or row["schema_version"] != transition.schema_version
                    ):
                        return rejected
                    envelope = self._envelope_from_row(
                        row,
                        object_kind="journal_entry",
                        object_id=transition.record_id,
                        domain_id=domain_id,
                        epoch=epoch,
                        sequence=sequence,
                        schema_version=transition.schema_version,
                    )
                    entry_payload = journal_entry_payload(
                        JournalEntry(
                            ConsistencyPosition(domain_id, epoch, sequence),
                            transition,
                        )
                    )
                    if (
                        envelope.previous_commitment != previous_commitment
                        or object_commitment(entry_payload) != envelope.object_commitment
                    ):
                        return rejected
                    entry = JournalEntry(
                        ConsistencyPosition(domain_id, epoch, sequence),
                        transition,
                        envelope,
                    )
                    if checkpoint is not None and sequence == checkpoint_sequence + 1:
                        if (
                            transition.record_kind is not ConsistencyRecordKind.CHECKPOINT_COMMITTED
                            or transition.record_id != checkpoint.checkpoint_id
                            or transition.operation_id != f"checkpoint:{checkpoint.checkpoint_id}"
                            or transition.checkpoint_reference != checkpoint.state_reference
                            or transition.occurred_at != checkpoint.created_at
                        ):
                            return rejected
                    entries.append(entry)
                    previous_commitment = envelope.object_commitment
                    expected_sequence += 1

                if checkpoint is None and any(
                    entry.transition.record_kind is ConsistencyRecordKind.CHECKPOINT_COMMITTED
                    for entry in entries
                ):
                    return rejected
                if checkpoint is not None and (
                    not entries
                    or entries[0].transition.record_kind
                        is not ConsistencyRecordKind.CHECKPOINT_COMMITTED
                    or any(
                        entry.transition.record_kind
                            is ConsistencyRecordKind.CHECKPOINT_COMMITTED
                        for entry in entries[1:]
                    )
                ):
                    return rejected
                if (
                    expected_sequence - 1 != head
                    or previous_commitment != domain["head_commitment"]
                ):
                    return rejected

                connection.commit()
                state = ConsistencyRecoveryState(
                    domain_id, epoch, checkpoint, tuple(entries), head,
                    domain["head_commitment"],
                )
                return ConsistencyRecoveryLoadResult(
                    ConsistencyRecoveryLoadStatus.LOADED, state
                )
        except sqlite3.Error:
            return unavailable
        except Exception:
            return rejected

    def load_recovery_state(
        self, domain_id: str,
    ) -> ConsistencyRecoveryState | None:
        """Diagnostic structural read; never an operational reducer input."""
        result = self.load_recovery_state_result(domain_id)
        return result.state if result.status is ConsistencyRecoveryLoadStatus.LOADED else None

    def load_verified_recovery_state(
        self, domain_id: str,
    ) -> ConsistencyRecoveryVerificationResult:
        """Authenticate and validate inventories before exposing local recovery evidence."""
        if self._recovery_verifier is None or self._recovery_trust_policy is None:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.UNAVAILABLE
            )

        loaded = self.load_recovery_state_result(domain_id)
        if loaded.status is ConsistencyRecoveryLoadStatus.UNAVAILABLE:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.UNAVAILABLE
            )
        if loaded.status is ConsistencyRecoveryLoadStatus.REJECTED:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.REJECTED
            )

        state = loaded.state
        if state is None:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.REJECTED
            )
        if state.domain_id != self._recovery_trust_policy.consistency_domain_id:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.REJECTED
            )

        try:
            context = ConsistencyRecoveryTrustContext(
                consistency_domain_id=state.domain_id,
                authority_epoch=state.authority_epoch,
                trust_policy_version=self._recovery_trust_policy.policy_version,
                verification_time=datetime.now(timezone.utc),
                purpose="sqlite-local-journal-recovery",
            )
        except Exception:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.UNAVAILABLE
            )

        try:
            return self._recovery_verifier.verify_recovery_state(state, context)
        except Exception:
            return ConsistencyRecoveryVerificationResult(
                ConsistencyRecoveryVerificationStatus.UNAVAILABLE
            )
