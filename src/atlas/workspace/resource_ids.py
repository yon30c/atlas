"""Canonical identifiers for exact Workspace CAM resources."""

import json

from atlas.core.errors import ContractError


def is_canonical_relative_file_path(path: str) -> bool:
    """Return whether a path is a normalized, safe relative POSIX file path."""
    if (
        not isinstance(path, str)
        or not path
        or path.strip() != path
        or "\x00" in path
        or "\\" in path
        or path.startswith("/")
        or (len(path) >= 2 and path[1] == ":")
        or "*" in path
        or "?" in path
    ):
        return False
    parts = path.split("/")
    return (
        all(part not in ("", ".", "..") for part in parts)
        and parts[0] != ".atlas-staging"
    )


def workspace_file_resource_id(workspace_id: str, path: str) -> str:
    """Build the exact stable CAM resource ID for a file in a Workspace."""
    if (
        not isinstance(workspace_id, str)
        or not workspace_id
        or workspace_id.strip() != workspace_id
        or not is_canonical_relative_file_path(path)
    ):
        raise ContractError("workspace_id/path no forman un recurso canónico")
    return json.dumps(
        [workspace_id, path],
        ensure_ascii=False,
        separators=(",", ":"),
    )
