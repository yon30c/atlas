"""Security and behavior tests for the isolated offline bootstrap CLI."""

from contextlib import closing
from datetime import timedelta
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from atlas.adapters.sqlite import SQLITE_MIGRATIONS, SQLiteDatabase, SQLiteIdentityAuthority
from atlas.core.identity import IdentityStatus
from atlas.platform_admin_bootstrap_cli import main


class FakeTTY:
    def __init__(self, fd: int, is_tty: bool = True):
        self.fd = fd
        self._is_tty = is_tty

    def isatty(self):
        return self._is_tty

    def fileno(self):
        return self.fd


class PlatformAdminBootstrapCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "authority.sqlite3"
        self.database = SQLiteDatabase(self.database_path)
        self.database.apply_migrations(SQLITE_MIGRATIONS)
        self.identity = SQLiteIdentityAuthority(self.database)
        self.user = self.identity.create_user()
        self.operation_id = str(uuid4())
        self.stdin = FakeTTY(0)
        self.stdout = FakeTTY(1)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run(self, *, user_id=None, operation_id=None, answer=None, stdin=None, stdout=None):
        output = []
        prompts = []

        def input_fn(prompt):
            prompts.append(prompt)
            return answer

        with (
            patch("atlas.platform_admin_bootstrap_cli.os.ttyname", return_value="/dev/pts/7"),
            patch("atlas.platform_admin_bootstrap_cli.os.getuid", return_value=1000),
            patch("atlas.platform_admin_bootstrap_cli.os.geteuid", return_value=1000),
        ):
            result = main(
                [
                    "--database", str(self.database_path),
                    "--user-id", user_id or self.user.user_id,
                    "--operation-id", operation_id or self.operation_id,
                ],
                input_fn=input_fn,
                output_fn=output.append,
                stdin=self.stdin if stdin is None else stdin,
                stdout=self.stdout if stdout is None else stdout,
            )
        return result, output, prompts

    def _count(self, table):
        with self.database.connection() as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_non_tty_aborts_before_prompt_or_write(self):
        result, output, prompts = self._run(
            answer=f"BOOTSTRAP PLATFORM ADMIN {self.user.user_id}",
            stdin=FakeTTY(0, is_tty=False),
        )
        self.assertEqual(result, 2)
        self.assertEqual(prompts, [])
        self.assertIn("TTY real", " ".join(output))
        self.assertEqual(self._count("platform_admin_bootstrap_events"), 0)
        self.assertEqual(self._count("platform_admin_grants"), 0)

    def test_wrong_confirmation_writes_nothing(self):
        result, output, prompts = self._run(answer="yes")
        self.assertEqual(result, 2)
        self.assertEqual(len(prompts), 1)
        self.assertIn("frase de confirmación incorrecta", " ".join(output))
        self.assertEqual(self._count("platform_admin_bootstrap_events"), 0)
        self.assertEqual(self._count("platform_admin_grants"), 0)

    def test_exact_confirmation_creates_one_grant_with_exact_permissions_and_ttl(self):
        phrase = f"BOOTSTRAP PLATFORM ADMIN {self.user.user_id}"
        result, output, _ = self._run(answer=phrase)
        self.assertEqual(result, 0, output)
        self.assertEqual(self._count("platform_admin_bootstrap_events"), 1)
        self.assertEqual(self._count("platform_admin_grants"), 1)
        grant = next(
            line.split(": ", 1)[1]
            for line in output if line.startswith("grant_id: ")
        )
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT issued_at, expires_at, permissions_json FROM platform_admin_grants WHERE grant_id = ?",
                (grant,),
            ).fetchone()
        from datetime import datetime
        self.assertEqual(
            datetime.fromisoformat(row["expires_at"]) - datetime.fromisoformat(row["issued_at"]),
            timedelta(days=90),
        )
        self.assertEqual(
            row["permissions_json"],
            '["association.reactivate","association.suspend"]',
        )

    def test_exact_replay_recovers_without_prompt_or_second_write_even_if_user_is_suspended(self):
        phrase = f"BOOTSTRAP PLATFORM ADMIN {self.user.user_id}"
        first, first_output, _ = self._run(answer=phrase)
        self.assertEqual(first, 0, first_output)
        original_grant_id = next(
            line.split(": ", 1)[1]
            for line in first_output if line.startswith("grant_id: ")
        )
        self.identity.update_user_status(
            self.user.user_id,
            expected_revision=self.user.identity.revision,
            status=IdentityStatus.SUSPENDED,
        )
        replay, replay_output, prompts = self._run(answer=None)
        self.assertEqual(replay, 0, replay_output)
        self.assertEqual(prompts, [])
        self.assertIn("ya estaba confirmada", " ".join(replay_output))
        self.assertIn(f"grant_id: {original_grant_id}", replay_output)
        self.assertEqual(self._count("platform_admin_bootstrap_events"), 1)
        self.assertEqual(self._count("platform_admin_grants"), 1)

    def test_operation_id_reused_for_another_user_is_rejected(self):
        phrase = f"BOOTSTRAP PLATFORM ADMIN {self.user.user_id}"
        first, _, _ = self._run(answer=phrase)
        self.assertEqual(first, 0)
        other = self.identity.create_user()
        result, output, prompts = self._run(
            user_id=other.user_id,
            operation_id=self.operation_id,
            answer=f"BOOTSTRAP PLATFORM ADMIN {other.user_id}",
        )
        self.assertEqual(result, 2)
        self.assertEqual(prompts, [])
        self.assertIn("otra intención", " ".join(output))
        self.assertEqual(self._count("platform_admin_bootstrap_events"), 1)
        self.assertEqual(self._count("platform_admin_grants"), 1)

    def test_relative_database_path_is_rejected_without_creating_a_file(self):
        output = []
        relative_path = Path(f"{uuid4()}.sqlite3")
        with (
            patch("atlas.platform_admin_bootstrap_cli.os.ttyname", return_value="/dev/pts/7"),
            patch("atlas.platform_admin_bootstrap_cli.os.getuid", return_value=1000),
            patch("atlas.platform_admin_bootstrap_cli.os.geteuid", return_value=1000),
        ):
            result = main(
                ["--database", str(relative_path), "--user-id", self.user.user_id,
                 "--operation-id", self.operation_id],
                output_fn=output.append,
                stdin=self.stdin,
                stdout=self.stdout,
            )
        self.assertEqual(result, 2)
        self.assertIn("ruta absoluta", " ".join(output))
        self.assertFalse(relative_path.exists())

    def test_missing_database_is_not_created(self):
        missing = Path(self.temp_dir.name) / "missing.sqlite3"
        output = []
        with (
            patch("atlas.platform_admin_bootstrap_cli.os.ttyname", return_value="/dev/pts/7"),
            patch("atlas.platform_admin_bootstrap_cli.os.getuid", return_value=1000),
            patch("atlas.platform_admin_bootstrap_cli.os.geteuid", return_value=1000),
        ):
            result = main(
                ["--database", str(missing), "--user-id", self.user.user_id,
                 "--operation-id", self.operation_id],
                output_fn=output.append,
                stdin=self.stdin,
                stdout=self.stdout,
            )
        self.assertEqual(result, 2)
        self.assertFalse(missing.exists())


    def test_stdout_must_be_a_tty_too(self):
        result, output, prompts = self._run(
            answer=f"BOOTSTRAP PLATFORM ADMIN {self.user.user_id}",
            stdout=FakeTTY(1, is_tty=False),
        )
        self.assertEqual(result, 2)
        self.assertEqual(prompts, [])
        self.assertIn("stdout", " ".join(output))
        self.assertEqual(self._count("platform_admin_bootstrap_events"), 0)

    def test_incomplete_schema_ledger_is_rejected_without_migration(self):
        incomplete = Path(self.temp_dir.name) / "incomplete.sqlite3"
        with closing(sqlite3.connect(incomplete)) as connection:
            connection.execute(
                "CREATE TABLE schema_migrations (version INTEGER, name TEXT, checksum TEXT)"
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, name, checksum) VALUES (1, 'partial', 'bad')"
            )
            connection.commit()
        output = []
        with (
            patch("atlas.platform_admin_bootstrap_cli.os.ttyname", return_value="/dev/pts/7"),
            patch("atlas.platform_admin_bootstrap_cli.os.getuid", return_value=1000),
            patch("atlas.platform_admin_bootstrap_cli.os.geteuid", return_value=1000),
        ):
            result = main(
                ["--database", str(incomplete), "--user-id", self.user.user_id,
                 "--operation-id", self.operation_id],
                output_fn=output.append,
                stdin=self.stdin,
                stdout=self.stdout,
            )
        self.assertEqual(result, 2)
        self.assertIn("schema no soportado", " ".join(output))
        with closing(sqlite3.connect(incomplete)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
