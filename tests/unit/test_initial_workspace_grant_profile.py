"""Tests for the exact owner-approved initial Workspace Grant profile."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import unittest

from atlas.authorization.initial_workspace_grant_profile import (
    InitialWorkspaceGrantDescriptor,
    build_initial_workspace_grants,
    workspace_file_resource_id,
)
from atlas.core.errors import ContractError
from atlas.core.identity import Identity, IdentityKind, IdentityStatus
from atlas.core.user_identity import CanonicalUserIdentity


NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def _owner(status=IdentityStatus.ACTIVE):
    return CanonicalUserIdentity(
        user_id=str(uuid4()),
        identity=Identity(
            identity_id=str(uuid4()),
            kind=IdentityKind.USER,
            status=status,
        ),
    )


def _descriptor(paths=("README.md", "docs/PROJECT_CONTEXT.md")):
    return InitialWorkspaceGrantDescriptor(
        project_id=str(uuid4()),
        environment_id=str(uuid4()),
        workspace_id="workspace-main",
        list_grant_id=str(uuid4()),
        read_grant_id=str(uuid4()) if paths else None,
        selected_file_paths=paths,
        issued_at=NOW,
    )


class InitialWorkspaceGrantProfileTests(unittest.TestCase):
    def test_builds_two_exact_grants_with_shared_owner_scope_and_expiry(self):
        owner = _owner()
        descriptor = _descriptor()
        grants = build_initial_workspace_grants(owner, descriptor)

        self.assertEqual(len(grants), 2)
        listing, reading = grants
        self.assertEqual(listing.grant_id, descriptor.list_grant_id)
        self.assertEqual(reading.grant_id, descriptor.read_grant_id)
        for grant in grants:
            self.assertEqual(grant.owner_user_id, owner.user_id)
            self.assertEqual(grant.subject_identity_id, owner.identity.identity_id)
            self.assertEqual(grant.project_id, descriptor.project_id)
            self.assertEqual(grant.environment, descriptor.environment_id)
            self.assertEqual(grant.issued_at, NOW)
            self.assertEqual(grant.expires_at, NOW + timedelta(days=7))
            self.assertEqual(grant.revision, 1)

        self.assertEqual(listing.resource_type, "workspace")
        self.assertEqual(listing.resource_ids, frozenset({"workspace-main"}))
        self.assertEqual(listing.actions, frozenset({"workspace.list"}))
        self.assertEqual(reading.resource_type, "workspace_file")
        self.assertEqual(
            reading.resource_ids,
            frozenset({
                workspace_file_resource_id("workspace-main", "README.md"),
                workspace_file_resource_id(
                    "workspace-main", "docs/PROJECT_CONTEXT.md"
                ),
            }),
        )
        self.assertEqual(reading.actions, frozenset({"workspace.read"}))

    def test_empty_file_allowlist_builds_only_workspace_list_grant(self):
        descriptor = _descriptor(paths=())
        grants = build_initial_workspace_grants(_owner(), descriptor)
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].actions, frozenset({"workspace.list"}))

    def test_rejects_missing_read_grant_id_for_nonempty_allowlist(self):
        with self.assertRaises(ContractError):
            InitialWorkspaceGrantDescriptor(
                project_id="project",
                environment_id="environment",
                workspace_id="workspace",
                list_grant_id=str(uuid4()),
                read_grant_id=None,
                selected_file_paths=("README.md",),
                issued_at=NOW,
            )

    def test_rejects_read_grant_id_without_selected_files(self):
        with self.assertRaises(ContractError):
            InitialWorkspaceGrantDescriptor(
                project_id="project",
                environment_id="environment",
                workspace_id="workspace",
                list_grant_id=str(uuid4()),
                read_grant_id=str(uuid4()),
                selected_file_paths=(),
                issued_at=NOW,
            )

    def test_rejects_wildcard_workspace_id(self):
        with self.assertRaises(ContractError):
            InitialWorkspaceGrantDescriptor(
                project_id="project",
                environment_id="environment",
                workspace_id="workspace*",
                list_grant_id=str(uuid4()),
                read_grant_id=None,
                selected_file_paths=(),
                issued_at=NOW,
            )

    def test_rejects_duplicate_grant_ids(self):
        grant_id = str(uuid4())
        with self.assertRaises(ContractError):
            InitialWorkspaceGrantDescriptor(
                project_id="project",
                environment_id="environment",
                workspace_id="workspace",
                list_grant_id=grant_id,
                read_grant_id=grant_id,
                selected_file_paths=("README.md",),
                issued_at=NOW,
            )

    def test_rejects_noncanonical_or_unsafe_paths(self):
        for path in (
            "../secret",
            "/etc/passwd",
            "a//b",
            "a/./b",
            "a/../b",
            ".atlas-staging/private",
            "wild*card.txt",
            "query?.txt",
            "C:/Windows/win.ini",
            "folder\\file.txt",
            " trailing.txt",
        ):
            with self.subTest(path=path):
                with self.assertRaises(ContractError):
                    _descriptor(paths=(path,))

    def test_rejects_duplicate_paths(self):
        with self.assertRaises(ContractError):
            _descriptor(paths=("README.md", "README.md"))

    def test_rejects_inactive_owner(self):
        with self.assertRaises(ContractError):
            build_initial_workspace_grants(
                _owner(IdentityStatus.SUSPENDED),
                _descriptor(),
            )

    def test_rejects_noncanonical_identity_pair(self):
        owner = CanonicalUserIdentity(
            user_id=str(uuid4()),
            identity=Identity(
                identity_id="not-a-canonical-uuid",
                kind=IdentityKind.USER,
                status=IdentityStatus.ACTIVE,
            ),
        )
        with self.assertRaises(ContractError):
            build_initial_workspace_grants(owner, _descriptor())

    def test_workspace_file_resource_id_is_compact_and_unicode_safe(self):
        self.assertEqual(
            workspace_file_resource_id("workspace", "datos/niño.txt"),
            '["workspace","datos/niño.txt"]',
        )


if __name__ == "__main__":
    unittest.main()
