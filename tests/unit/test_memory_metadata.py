import unittest

from atlas.core.errors import ContractError
from atlas.memory.metadata import (
    EnvironmentMetadata,
    MemoryVersionMetadata,
    ProjectMetadata,
)
from atlas.memory.models import MemoryVersionStatus


MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
PARENT_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"


class MemoryMetadataTests(unittest.TestCase):
    def test_version_metadata_accepts_minimal_valid_snapshot(self):
        metadata = MemoryVersionMetadata(
            version_id=VERSION_ID,
            memory_id=MEMORY_ID,
            status=MemoryVersionStatus.APPROVED,
            parent_version_id=PARENT_ID,
        )
        self.assertEqual(metadata.memory_id, MEMORY_ID)
        self.assertEqual(metadata.parent_version_id, PARENT_ID)

    def test_version_metadata_rejects_invalid_identifiers(self):
        with self.assertRaises(ContractError):
            MemoryVersionMetadata(
                version_id="not-a-uuid",
                memory_id=MEMORY_ID,
                status=MemoryVersionStatus.APPROVED,
                parent_version_id=None,
            )

    def test_version_metadata_rejects_unknown_status_type(self):
        with self.assertRaises(ContractError):
            MemoryVersionMetadata(
                version_id=VERSION_ID,
                memory_id=MEMORY_ID,
                status="approved",
                parent_version_id=None,
            )

    def test_project_metadata_preserves_canonical_status(self):
        self.assertEqual(ProjectMetadata("project-001", "active").status, "active")
        with self.assertRaises(ContractError):
            ProjectMetadata("", "active")
        with self.assertRaises(ContractError):
            ProjectMetadata("project-001", " ")

    def test_environment_metadata_preserves_canonical_status(self):
        self.assertEqual(EnvironmentMetadata("development", "active").status, "active")
        with self.assertRaises(ContractError):
            EnvironmentMetadata(" ", "active")
        with self.assertRaises(ContractError):
            EnvironmentMetadata("development", " ")


if __name__ == "__main__":
    unittest.main()
