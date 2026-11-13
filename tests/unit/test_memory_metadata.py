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

    def test_project_metadata_requires_opaque_id_and_boolean_state(self):
        self.assertTrue(ProjectMetadata("project-001", True).is_active)
        with self.assertRaises(ContractError):
            ProjectMetadata("", True)
        with self.assertRaises(ContractError):
            ProjectMetadata("project-001", "active")

    def test_environment_metadata_requires_opaque_id_and_boolean_state(self):
        self.assertTrue(EnvironmentMetadata("development", True).is_active)
        with self.assertRaises(ContractError):
            EnvironmentMetadata(" ", True)
        with self.assertRaises(ContractError):
            EnvironmentMetadata("development", 1)


if __name__ == "__main__":
    unittest.main()
