"""Pruebas del catálogo cerrado de capacidades."""

import unittest

from atlas.assistant.capabilities import (
    CapabilityCatalog,
    CapabilityDefinition,
    CapabilityRisk,
    build_default_capability_catalog,
)
from atlas.assistant.planning import AssistantIntent, IntentKind
from atlas.core.errors import ContractError


class CapabilityCatalogTests(unittest.TestCase):
    def test_default_catalog_contains_only_list_and_read(self):
        catalog = build_default_capability_catalog()
        self.assertEqual(
            tuple(item.kind for item in catalog.list_all()),
            (IntentKind.WORKSPACE_LIST, IntentKind.WORKSPACE_READ),
        )
        self.assertTrue(all(item.risk is CapabilityRisk.READ_ONLY for item in catalog.list_all()))
        self.assertIsNone(catalog.get(IntentKind.WORKSPACE_WRITE)) if hasattr(IntentKind, "WORKSPACE_WRITE") else None

    def test_catalog_lookup_returns_definition_without_handler(self):
        catalog = build_default_capability_catalog()
        definition = catalog.get(IntentKind.WORKSPACE_READ)
        self.assertEqual(definition.parameter_names, ("workspace_id", "path"))
        self.assertEqual(definition.result_type, "WorkspaceFile")
        self.assertFalse(hasattr(definition, "handler"))

    def test_validates_exact_intent_parameters(self):
        catalog = build_default_capability_catalog()
        intent = AssistantIntent(
            IntentKind.WORKSPACE_READ,
            (("workspace_id", "demo"), ("path", "notes.txt")),
        )
        self.assertIs(catalog.validate_intent(intent), catalog.get(IntentKind.WORKSPACE_READ))
        with self.assertRaises(ContractError):
            catalog.validate_intent(AssistantIntent(
                IntentKind.WORKSPACE_READ, (("workspace_id", "demo"),)
            ))

    def test_rejects_duplicate_and_mutable_definitions(self):
        definition = CapabilityDefinition(
            IntentKind.WORKSPACE_LIST, "list", ("workspace_id",),
            CapabilityRisk.READ_ONLY, "WorkspaceListing",
        )
        with self.assertRaises(ContractError):
            CapabilityCatalog((definition, definition))
        with self.assertRaises(ContractError):
            CapabilityCatalog([definition])

    def test_rejects_duplicate_parameter_names(self):
        with self.assertRaises(ContractError):
            CapabilityDefinition(
                IntentKind.WORKSPACE_READ, "read", ("workspace_id", "workspace_id"),
                CapabilityRisk.READ_ONLY, "WorkspaceFile",
            )


if __name__ == "__main__":
    unittest.main()
