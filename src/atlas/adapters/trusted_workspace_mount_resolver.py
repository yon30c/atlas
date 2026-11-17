"""Trusted deployment mapping from symbolic mount references to local roots."""

import re
import stat
from pathlib import Path
from typing import Mapping

from atlas.core.errors import ContractError


_MOUNT_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)


class TrustedWorkspaceMountResolver:
    """Resolve registry root_ref values using an immutable trusted mount map.

    The caller supplies only a symbolic root_ref. Physical paths are accepted
    exclusively at trusted composition time and are revalidated on every use.
    """

    def __init__(self, mounts: Mapping[str, str | Path]) -> None:
        if not isinstance(mounts, Mapping) or not mounts:
            raise ContractError("mounts debe ser un mapa confiable no vacío")

        configured: dict[str, Path] = {}
        for mount_id, root_value in mounts.items():
            if (
                not isinstance(mount_id, str)
                or _MOUNT_ID.fullmatch(mount_id) is None
            ):
                raise ContractError("mount_id tiene un formato inválido")
            try:
                root = Path(root_value)
            except (TypeError, ValueError) as exc:
                raise ContractError("la raíz del mount debe ser una ruta válida") from exc
            if not root.is_absolute():
                raise ContractError("la raíz del mount debe ser absoluta")
            configured[mount_id] = self._validate_root(root)

        self._mounts = configured

    @staticmethod
    def _validate_root(root: Path) -> Path:
        try:
            metadata = root.lstat()
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise ContractError("la raíz del mount debe existir") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or resolved != root
        ):
            raise ContractError("la raíz del mount debe ser un directorio real y canónico")
        return root

    def resolve(self, root_ref: str) -> Path:
        """Resolve exactly mount:<id>; never accepts or normalizes physical paths."""
        if not isinstance(root_ref, str) or not root_ref.startswith("mount:"):
            raise ContractError("root_ref debe usar el formato mount:<id>")
        mount_id = root_ref[6:]
        if _MOUNT_ID.fullmatch(mount_id) is None:
            raise ContractError("root_ref contiene un mount_id inválido")
        root = self._mounts.get(mount_id)
        if root is None:
            raise ContractError("root_ref no corresponde a un mount confiable")
        return self._validate_root(root)
