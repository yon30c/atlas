import unittest

from atlas.authorization.resource_metadata import ResourceMetadataResolver
from atlas.core.errors import ContractError


class StubReader:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requested_ids = []

    def get_metadata(self, resource_id):
        self.requested_ids.append(resource_id)
        if self.error is not None:
            raise self.error
        return self.result


class ResourceMetadataResolverTests(unittest.TestCase):
    def test_routes_to_reader_registered_for_exact_resource_type(self):
        memory_reader = StubReader({"owner_id": "owner-1"})
        project_reader = StubReader({"status": "active"})
        resolver = ResourceMetadataResolver({
            "memory": memory_reader,
            "project": project_reader,
        })

        result = resolver.resolve("memory", "memory-1")

        self.assertEqual(result, {"owner_id": "owner-1"})
        self.assertEqual(memory_reader.requested_ids, ["memory-1"])
        self.assertEqual(project_reader.requested_ids, [])

    def test_unknown_resource_type_fails_closed_without_fallback(self):
        reader = StubReader({"owner_id": "owner-1"})
        resolver = ResourceMetadataResolver({"memory": reader})

        self.assertIsNone(resolver.resolve("unknown", "resource-1"))
        self.assertEqual(reader.requested_ids, [])

    def test_missing_or_invalid_identifiers_fail_closed(self):
        reader = StubReader({"owner_id": "owner-1"})
        resolver = ResourceMetadataResolver({"memory": reader})

        for resource_type, resource_id in (
            ("", "memory-1"),
            ("memory", ""),
            ("memory", None),
            (None, "memory-1"),
        ):
            with self.subTest(resource_type=resource_type, resource_id=resource_id):
                self.assertIsNone(resolver.resolve(resource_type, resource_id))
        self.assertEqual(reader.requested_ids, [])

    def test_missing_metadata_fails_closed(self):
        resolver = ResourceMetadataResolver({"memory": StubReader(None)})
        self.assertIsNone(resolver.resolve("memory", "memory-1"))

    def test_reader_exception_fails_closed(self):
        reader = StubReader(error=TimeoutError("metadata source unavailable"))
        resolver = ResourceMetadataResolver({"memory": reader})

        self.assertIsNone(resolver.resolve("memory", "memory-1"))

    def test_invalid_registry_is_rejected(self):
        with self.assertRaises(ContractError):
            ResourceMetadataResolver(None)
        with self.assertRaises(ContractError):
            ResourceMetadataResolver({"memory": object()})
        with self.assertRaises(ContractError):
            ResourceMetadataResolver({"": StubReader()})

    def test_registry_is_defensively_copied(self):
        reader = StubReader("metadata")
        registry = {"memory": reader}
        resolver = ResourceMetadataResolver(registry)
        registry.clear()

        self.assertEqual(
            resolver.resolve("memory", "memory-1"),
            "metadata",
        )


if __name__ == "__main__":
    unittest.main()
