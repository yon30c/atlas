"""Host-boundary tests for the dedicated offline provisioning entrypoint."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.offline_association_provisioning_cli import (
    _parse_operation_id,
    _require_current_schema,
    _require_sudo_tty,
)
from atlas.core.errors import ContractError


class _TTY:
    def __init__(self, descriptor, is_tty=True):
        self.descriptor = descriptor
        self._is_tty = is_tty

    def isatty(self):
        return self._is_tty

    def fileno(self):
        return self.descriptor


class OfflineAssociationProvisioningCLITests(unittest.TestCase):
    def test_sudo_requires_non_root_real_uid_root_effective_uid_and_matching_tty(self):
        with (
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getuid", return_value=1000),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.geteuid", return_value=0),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.ttyname", return_value="/dev/pts/7"),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.tcgetpgrp", return_value=42),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getpgrp", return_value=42),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.sys.stdin", _TTY(0)),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.sys.stdout", _TTY(1)),
            patch.dict(os.environ, {"SUDO_UID": "1000"}),
        ):
            self.assertEqual(_require_sudo_tty(), (1000, 0, "/dev/pts/7"))

    def test_non_root_effective_uid_is_denied(self):
        with (
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getuid", return_value=1000),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.geteuid", return_value=1000),
            patch.dict(os.environ, {"SUDO_UID": "1000"}),
        ):
            with self.assertRaises(PermissionError):
                _require_sudo_tty()

    def test_root_real_uid_is_denied_even_with_effective_root(self):
        with (
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getuid", return_value=0),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.geteuid", return_value=0),
            patch.dict(os.environ, {"SUDO_UID": "0"}),
        ):
            with self.assertRaises(PermissionError):
                _require_sudo_tty()

    def test_background_process_group_is_denied(self):
        with (
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getuid", return_value=1000),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.geteuid", return_value=0),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.ttyname", return_value="/dev/pts/7"),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.tcgetpgrp", return_value=99),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getpgrp", return_value=42),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.sys.stdin", _TTY(0)),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.sys.stdout", _TTY(1)),
            patch.dict(os.environ, {"SUDO_UID": "1000"}),
        ):
            with self.assertRaises(PermissionError):
                _require_sudo_tty()

    def test_piped_input_is_denied(self):
        with (
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.getuid", return_value=1000),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.os.geteuid", return_value=0),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.sys.stdin", _TTY(0, False)),
            patch("atlas.adapters.sqlite.offline_association_provisioning_cli.sys.stdout", _TTY(1, True)),
            patch.dict(os.environ, {"SUDO_UID": "1000"}),
        ):
            with self.assertRaises(PermissionError):
                _require_sudo_tty()

    def test_database_schema_must_match_full_migration_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = SQLiteDatabase(Path(directory) / "authority.sqlite")
            database.apply_migrations(SQLITE_MIGRATIONS)
            _require_current_schema(database)
            with database.connection() as connection:
                connection.execute(
                    "UPDATE schema_migrations SET checksum = ? WHERE version = 28",
                    ("0" * 64,),
                )
            with self.assertRaises(ContractError):
                _require_current_schema(database)

    def test_operation_id_must_be_canonical_uuid4(self):
        self.assertEqual(_parse_operation_id("d9428888-122b-4f4b-8f4b-1f5e3b6c9a10"),
                         "d9428888-122b-4f4b-8f4b-1f5e3b6c9a10")
        with self.assertRaises(Exception):
            _parse_operation_id("not-a-uuid")


if __name__ == "__main__":
    unittest.main()
