import unittest

from atlas.memory.errors import MemoryContractError
from atlas.memory.metadata import (
    EnvironmentMetadata,
    MemoryVersionMetadata,
    ProjectMetadata,
)
from atlas.memory.models import MemoryClassification, MemoryVersionStatus


MEMORY_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a11"
VERSION_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a12"
PARENT_ID = "018bcfe5-7b3a-7cc2-98c4-dc0c0c073a13"


class MemoryMetadataTests(unittest.TestCase):
    def test_version_metadata_accepts_minimal_valid_snapshot(self):
        metadata = MemoryVersionMetadata(
            version_id=VERSION_ID,
            memory_id=MEMORY_ID,
            status=MemoryVersionStatus.APPROVED,
            classification=MemoryClassification.CONFIDENTIAL,
            parent_version_id=PARENT_ID,
            revision=1,
        )
        self.assertEqual(metadata.memory_id, MEMORY_ID)
        self.assertEqual(metadata.parent_version_id, PARENT_ID)
        self.assertEqual(metadata.classification, MemoryClassification.CONFIDENTIAL)

    def test_version_metadata_rejects_invalid_identifiers(self):
        with self.assertRaises(MemoryContractError):
            MemoryVersionMetadata(
                version_id="not-a-uuid",
                memory_id=MEMORY_ID,
                status=MemoryVersionStatus.APPROVED,
                classification=MemoryClassification.CONFIDENTIAL,
                parent_version_id=None,
                revision=1,
            )

    def test_version_metadata_rejects_unknown_status_type(self):
        with self.assertRaises(MemoryContractError):
            MemoryVersionMetadata(
                version_id=VERSION_ID,
                memory_id=MEMORY_ID,
                status="approved",
                classification=MemoryClassification.CONFIDENTIAL,
                parent_version_id=None,
                revision=1,
            )

    def test_version_metadata_rejects_unknown_classification_type(self):
        with self.assertRaises(MemoryContractError):
            MemoryVersionMetadata(
                version_id=VERSION_ID,
                memory_id=MEMORY_ID,
                status=MemoryVersionStatus.APPROVED,
                classification="RESTRICTED",
                parent_version_id=None,
                revision=1,
            )

    def test_project_metadata_preserves_canonical_status(self):
        self.assertEqual(ProjectMetadata("project-001", "active", 1).status, "active")
        with self.assertRaises(MemoryContractError):
            ProjectMetadata("", "active", 1)
        with self.assertRaises(MemoryContractError):
            ProjectMetadata("project-001", " ", 1)

    def test_environment_metadata_preserves_canonical_status(self):
        self.assertEqual(EnvironmentMetadata("development", "active", 1).status, "active")
        with self.assertRaises(MemoryContractError):
            EnvironmentMetadata(" ", "active", 1)
        with self.assertRaises(MemoryContractError):
            EnvironmentMetadata("development", " ", 1)


if __name__ == "__main__":
    unittest.main()
