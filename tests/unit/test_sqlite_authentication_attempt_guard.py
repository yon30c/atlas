from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest

from atlas.adapters.sqlite.authentication_attempt_guard import (
    SQLiteAuthenticationAttemptGuard,
)
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.ports.authentication_attempt_guard import (
    AuthenticationAttemptDenied,
    AuthenticationAttemptReservationError,
)


class SQLiteAuthenticationAttemptGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = SQLiteDatabase(Path(self.temp_dir.name) / "attempt-guard.sqlite")
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.guard = SQLiteAuthenticationAttemptGuard(self.database)
        self.issuer_id = "issuer-test"
        self.handle = "atlas.owner"
        self.now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)

    def _failure(self, at):
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=at
        )
        self.guard.complete_failure(reservation, at=at)

    def _rows(self, table):
        with self.database.connection() as connection:
            return connection.execute(f"SELECT * FROM {table}").fetchall()

    def test_schema_migration_creates_guard_tables(self):
        with self.database.connection() as connection:
            names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertIn("native_authentication_attempt_reservations", names)
        self.assertIn("native_authentication_attempt_failures", names)

    def test_two_concurrent_reservations_are_allowed_but_third_is_denied(self):
        barrier = threading.Barrier(3)

        def reserve(_):
            barrier.wait()
            try:
                return self.guard.begin_attempt(
                    self.issuer_id, self.handle, at=self.now
                )
            except AuthenticationAttemptDenied:
                return None

        with ThreadPoolExecutor(max_workers=3) as pool:
            reservations = list(pool.map(reserve, range(3)))

        accepted = [item for item in reservations if item is not None]
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(self._rows("native_authentication_attempt_reservations")), 2)
        for reservation in accepted:
            self.guard.abandon_attempt(reservation)
        self.assertEqual(self._rows("native_authentication_attempt_reservations"), [])

    def test_backoff_is_exactly_one_two_four_seven_and_fifteen_minutes(self):
        delays = (1, 2, 4, 7, 15)
        at = self.now

        for delay in delays:
            reservation = self.guard.begin_attempt(
                self.issuer_id, self.handle, at=at
            )
            self.guard.complete_failure(reservation, at=at)
            rows = self._rows("native_authentication_attempt_failures")
            latest = max(rows, key=lambda row: row["occurred_at"])
            self.assertEqual(
                latest["blocked_until"],
                (at + timedelta(minutes=delay)).isoformat(timespec="microseconds"),
            )
            at += timedelta(minutes=delay)

        self.assertEqual(len(self._rows("native_authentication_attempt_failures")), 5)
        with self.assertRaises(AuthenticationAttemptDenied):
            self.guard.begin_attempt(
                self.issuer_id, self.handle, at=at - timedelta(seconds=1)
            )
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=at
        )
        self.guard.abandon_attempt(reservation)

    def test_failure_window_expires_old_failures(self):
        self._failure(self.now)
        allowed_at = self.now + timedelta(minutes=1)
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=allowed_at
        )
        self.guard.abandon_attempt(reservation)

        after_window = self.now + timedelta(minutes=16)
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=after_window
        )
        self.guard.abandon_attempt(reservation)
        self.assertEqual(self._rows("native_authentication_attempt_failures"), [])

    def test_expired_reservation_is_rejected_and_deleted_durably(self):
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=self.now
        )
        with self.assertRaises(AuthenticationAttemptReservationError):
            self.guard.complete_failure(
                reservation, at=self.now + timedelta(seconds=121)
            )
        self.assertEqual(self._rows("native_authentication_attempt_reservations"), [])
        self.assertEqual(self._rows("native_authentication_attempt_failures"), [])

    def test_abandonment_does_not_count_as_failure(self):
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=self.now
        )
        self.guard.abandon_attempt(reservation)
        self.assertEqual(self._rows("native_authentication_attempt_failures"), [])
        next_reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=self.now
        )
        self.guard.abandon_attempt(next_reservation)

    def test_success_resets_failures_but_preserves_other_active_reservations(self):
        self._failure(self.now)
        at = self.now + timedelta(minutes=1)
        first = self.guard.begin_attempt(self.issuer_id, self.handle, at=at)
        second = self.guard.begin_attempt(self.issuer_id, self.handle, at=at)
        self.guard.complete_success(first, at=at)

        self.assertEqual(self._rows("native_authentication_attempt_failures"), [])
        reservations = self._rows("native_authentication_attempt_reservations")
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0]["reservation_id"], second.reservation_id)
        self.guard.abandon_attempt(second)

    def test_reservation_cannot_be_completed_twice(self):
        reservation = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=self.now
        )
        self.guard.complete_failure(reservation, at=self.now)
        with self.assertRaises(AuthenticationAttemptReservationError):
            self.guard.complete_success(reservation, at=self.now)
        self.assertEqual(len(self._rows("native_authentication_attempt_failures")), 1)

    def test_expired_reservations_are_cleaned_when_new_attempt_is_denied(self):
        first = self.guard.begin_attempt(self.issuer_id, self.handle, at=self.now)
        second = self.guard.begin_attempt(self.issuer_id, self.handle, at=self.now)
        with self.assertRaises(AuthenticationAttemptDenied):
            self.guard.begin_attempt(self.issuer_id, self.handle, at=self.now)
        denied_at = self.now + timedelta(seconds=121)
        replacement = self.guard.begin_attempt(
            self.issuer_id, self.handle, at=denied_at
        )
        self.assertEqual(len(self._rows("native_authentication_attempt_reservations")), 1)
        self.assertEqual(
            self._rows("native_authentication_attempt_reservations")[0]["reservation_id"],
            replacement.reservation_id,
        )
        self.guard.abandon_attempt(replacement)


if __name__ == "__main__":
    unittest.main()
