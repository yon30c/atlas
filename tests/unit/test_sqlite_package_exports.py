from atlas.adapters import sqlite


def test_workspace_registry_repository_is_exported_from_sqlite_package() -> None:
    assert "SQLiteWorkspaceRegistryRepository" in sqlite.__all__
    assert sqlite.SQLiteWorkspaceRegistryRepository.__module__ == (
        "atlas.adapters.sqlite.workspace_registry_repository"
    )
