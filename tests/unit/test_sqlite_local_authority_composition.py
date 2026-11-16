"""Tests for the shared local authority foundation composition."""

from pathlib import Path
import tempfile
import unittest

from atlas.adapters.sqlite.local_authority_composition import (
    SQLiteLocalAuthorityFoundation,
    compose_sqlite_local_authority,
)
from atlas.core.errors import ContractError


class SQLiteLocalAuthorityCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "authority.sqlite"

    def test_identity_grants_and_change_store_share_exact_database(self):
        composition = compose_sqlite_local_authority(self.path)

        self.assertIsInstance(composition, SQLiteLocalAuthorityFoundation)
        self.assertIs(composition.identity.database, composition.database)
        self.assertIs(composition.identity.authority._database, composition.database)
        self.assertIs(composition.grants._database, composition.database)
        self.assertIs(composition.authority_changes._database, composition.database)

        user = composition.identity.authority.create_user()
        self.assertEqual(
            composition.identity.authority.get_user(user.user_id),
            user,
        )

    def test_composition_migrates_grant_schema(self):
        composition = compose_sqlite_local_authority(self.path)
        with composition.database.connection() as connection:
            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertEqual(versions, [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertIn("authorization_grants", tables)
        self.assertIn("authority_change_operations", tables)

    def test_composition_contract_rejects_mismatched_database(self):
        first = compose_sqlite_local_authority(self.path)
        other = compose_sqlite_local_authority(
            Path(self.temp_dir.name) / "other.sqlite"
        )
        with self.assertRaises(ContractError):
            SQLiteLocalAuthorityFoundation(
                database=first.database,
                identity=other.identity,
                grants=first.grants,
                authority_changes=first.authority_changes,
            )


if __name__ == "__main__":
    unittest.main()
