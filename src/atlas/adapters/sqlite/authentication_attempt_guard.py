"""Shared SQLite implementation of the native authentication attempt guard."""

from datetime import datetime, timedelta
import hashlib
from uuid import uuid4

from atlas.authentication.credentials import LoginHandle
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.core.errors import ContractError
from atlas.ports.authentication_attempt_guard import (
    AuthenticationAttemptDenied,
    AuthenticationAttemptReservation,
    AuthenticationAttemptReservationError,
)


_WINDOW = timedelta(minutes=15)
_RESERVATION_TTL = timedelta(seconds=120)
_MAX_CONCURRENT = 2
_BACKOFF_MINUTES = (1, 2, 4, 7, 15)
_DOMAIN = b"atlas/native-authentication-attempt/v1\x00"


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError(f"{field} debe ser datetime con zona horaria")
    if value.utcoffset() != timedelta(0):
        raise ContractError(f"{field} debe estar en UTC")
    return value


def _timestamp(value: datetime, field: str) -> str:
    return _utc(value, field).isoformat(timespec="microseconds")


class SQLiteAuthenticationAttemptGuard:
    """Atomic cross-process throttling backed by the canonical SQLite file.

    Every method owns a short BEGIN IMMEDIATE transaction. Never call it from
    inside SQLiteLocalAuthorityUnitOfWork or while Argon2id is running.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    @staticmethod
    def _account_digest(issuer_id: str, login_handle: str) -> str:
        if not isinstance(issuer_id, str) or not issuer_id:
            raise ContractError("issuer_id debe ser no vacío")
        if not isinstance(login_handle, str) or not login_handle:
            raise ContractError("login_handle debe ser no vacío")
        normalized_handle = LoginHandle(login_handle).value
        material = (
            _DOMAIN
            + issuer_id.encode("utf-8")
            + b"\x00"
            + normalized_handle.encode("ascii")
        )
        return hashlib.sha256(material).hexdigest()

    @staticmethod
    def _reservation_id(reservation: AuthenticationAttemptReservation) -> str:
        if not isinstance(reservation, AuthenticationAttemptReservation):
            raise ContractError("reservation debe ser AuthenticationAttemptReservation")
        return reservation.reservation_id

    def begin_attempt(
        self, issuer_id: str, login_handle: str, *, at: datetime
    ) -> AuthenticationAttemptReservation:
        now = _utc(at, "at")
        now_text = _timestamp(now, "at")
        cutoff_text = _timestamp(now - _WINDOW, "window_start")
        account = self._account_digest(issuer_id, login_handle)
        reservation_id = str(uuid4())
        expires_at = now + _RESERVATION_TTL
        denied = False

        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                # Opportunistic bounded garbage collection also covers accounts
                # that never attempt another login. Active blocks are retained
                # until blocked_until, even when their source failure leaves the
                # rolling count window.
                connection.execute(
                    """
                    DELETE FROM native_authentication_attempt_reservations
                    WHERE reservation_id IN (
                        SELECT reservation_id
                        FROM native_authentication_attempt_reservations
                        WHERE expires_at <= ?
                        ORDER BY expires_at
                        LIMIT 256
                    )
                    """,
                    (now_text,),
                )
                connection.execute(
                    """
                    DELETE FROM native_authentication_attempt_failures
                    WHERE failure_id IN (
                        SELECT failure_id
                        FROM native_authentication_attempt_failures
                        WHERE occurred_at <= ? AND blocked_until <= ?
                        ORDER BY occurred_at
                        LIMIT 256
                    )
                    """,
                    (cutoff_text, now_text),
                )
                blocked = connection.execute(
                    """
                    SELECT MAX(blocked_until) AS blocked_until
                    FROM native_authentication_attempt_failures
                    WHERE account_digest = ? AND blocked_until > ?
                    """,
                    (account, now_text),
                ).fetchone()["blocked_until"]
                active = connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM native_authentication_attempt_reservations
                    WHERE account_digest = ? AND expires_at > ?
                    """,
                    (account, now_text),
                ).fetchone()["total"]
                denied = (blocked is not None and blocked > now_text) or (
                    active >= _MAX_CONCURRENT
                )
                if not denied:
                    connection.execute(
                        """
                        INSERT INTO native_authentication_attempt_reservations(
                            reservation_id, account_digest, expires_at
                        ) VALUES (?, ?, ?)
                        """,
                        (reservation_id, account, _timestamp(expires_at, "expires_at")),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

        if denied:
            raise AuthenticationAttemptDenied()
        return AuthenticationAttemptReservation(
            reservation_id=reservation_id,
            expires_at=expires_at,
        )

    def _consume(
        self,
        reservation: AuthenticationAttemptReservation,
        *,
        at: datetime,
        outcome: str,
    ) -> None:
        now = _utc(at, "at")
        now_text = _timestamp(now, "at")
        reservation_id = self._reservation_id(reservation)
        expired_or_missing = False

        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT account_digest, expires_at
                    FROM native_authentication_attempt_reservations
                    WHERE reservation_id = ?
                    """,
                    (reservation_id,),
                ).fetchone()
                if row is None:
                    expired_or_missing = True
                elif row["expires_at"] <= now_text:
                    connection.execute(
                        "DELETE FROM native_authentication_attempt_reservations "
                        "WHERE reservation_id = ?",
                        (reservation_id,),
                    )
                    expired_or_missing = True
                else:
                    account = row["account_digest"]
                    if outcome == "failure":
                        cutoff_text = _timestamp(now - _WINDOW, "window_start")
                        connection.execute(
                            "DELETE FROM native_authentication_attempt_failures "
                            "WHERE account_digest = ? AND occurred_at <= ?",
                            (account, cutoff_text),
                        )
                        previous = connection.execute(
                            """
                            SELECT COUNT(*) AS total
                            FROM native_authentication_attempt_failures
                            WHERE account_digest = ? AND occurred_at > ?
                            """,
                            (account, cutoff_text),
                        ).fetchone()["total"]
                        delay = _BACKOFF_MINUTES[
                            min(previous, len(_BACKOFF_MINUTES) - 1)
                        ]
                        connection.execute(
                            """
                            INSERT INTO native_authentication_attempt_failures(
                                failure_id, account_digest, occurred_at, blocked_until
                            ) VALUES (?, ?, ?, ?)
                            """,
                            (
                                str(uuid4()),
                                account,
                                now_text,
                                _timestamp(
                                    now + timedelta(minutes=delay), "blocked_until"
                                ),
                            ),
                        )
                    elif outcome == "success":
                        connection.execute(
                            "DELETE FROM native_authentication_attempt_failures "
                            "WHERE account_digest = ?",
                            (account,),
                        )
                    else:
                        raise ContractError("outcome interno inválido")

                    connection.execute(
                        "DELETE FROM native_authentication_attempt_reservations "
                        "WHERE reservation_id = ?",
                        (reservation_id,),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

        if expired_or_missing:
            raise AuthenticationAttemptReservationError(
                "reserva ausente, expirada o ya consumida"
            )

    def complete_failure(
        self, reservation: AuthenticationAttemptReservation, *, at: datetime
    ) -> None:
        self._consume(reservation, at=at, outcome="failure")

    def complete_success(
        self, reservation: AuthenticationAttemptReservation, *, at: datetime
    ) -> None:
        self._consume(reservation, at=at, outcome="success")

    def abandon_attempt(
        self, reservation: AuthenticationAttemptReservation
    ) -> None:
        reservation_id = self._reservation_id(reservation)
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM native_authentication_attempt_reservations "
                    "WHERE reservation_id = ?",
                    (reservation_id,),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
