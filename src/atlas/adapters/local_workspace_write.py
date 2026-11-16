"""Adaptador local de escritura con staging durable y recuperación explícita.

La garantía cubre escrituras cooperativas de Atlas dentro de un workspace local.
No sustituye CAM, no coordina escritores externos y no ofrece atomicidad con SQLite.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping
from uuid import UUID, uuid4

from atlas.assistant.workspace_write import (
    WorkspaceRecoveryAssessment,
    WorkspaceRecoveryStatus,
    WorkspaceWriteCommit,
    WorkspaceWriteStage,
    WorkspaceWriteState,
)
from atlas.core.errors import AtlasError, ConcurrencyError, ContractError, NotFoundError


DEFAULT_MAX_WRITE_BYTES = 1024 * 1024
_STAGING_DIRECTORY = ".atlas-staging"
_MANIFEST_NAME = "manifest.json"
_MANIFEST_KEYS = {
    "schema_version", "workspace_id", "operation_id", "path",
    "expected_sha256", "content_sha256", "size_bytes", "state",
}


class LocalWorkspaceWriteAdapter:
    """Prepara archivos fuera del destino y los aplica mediante commit explícito."""

    def __init__(
        self,
        workspaces: Mapping[str, str | Path],
        *,
        max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES,
    ) -> None:
        if not isinstance(workspaces, Mapping) or not workspaces:
            raise ContractError("workspaces debe ser un mapa no vacío")
        if isinstance(max_write_bytes, bool) or not isinstance(max_write_bytes, int) or max_write_bytes <= 0:
            raise ContractError("max_write_bytes debe ser un entero positivo")
        configured: dict[str, Path] = {}
        for workspace_id, value in workspaces.items():
            if not isinstance(workspace_id, str) or not workspace_id.strip() or workspace_id.strip() != workspace_id:
                raise ContractError("workspace_id debe ser texto normalizado")
            root = Path(value)
            if not root.is_absolute():
                raise ContractError("la raíz del workspace debe ser absoluta")
            try:
                metadata = root.lstat()
                resolved = root.resolve(strict=True)
            except OSError as exc:
                raise ContractError("la raíz del workspace debe existir") from exc
            if resolved != root or not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise ContractError("la raíz debe ser un directorio real y canónico")
            configured[workspace_id] = root
        self._workspaces = configured
        self._max_write_bytes = max_write_bytes

    def _root(self, workspace_id: str) -> Path:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ContractError("workspace_id debe ser texto no vacío")
        root = self._workspaces.get(workspace_id)
        if root is None:
            raise NotFoundError("workspace no configurado")
        return root

    @staticmethod
    def _operation_id(value: str) -> str:
        if not isinstance(value, str):
            raise ContractError("operation_id debe ser UUID")
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ContractError("operation_id debe ser UUID") from exc
        canonical = str(parsed)
        if canonical != value.lower():
            raise ContractError("operation_id debe usar formato UUID canónico")
        return canonical

    @staticmethod
    def _path_parts(path: str) -> tuple[str, ...]:
        if (
            not isinstance(path, str) or not path or path.strip() != path
            or "\x00" in path or "\\" in path or path.startswith("/")
            or (len(path) >= 2 and path[1] == ":")
        ):
            raise ContractError("path debe ser una ruta relativa POSIX normalizada")
        parts = tuple(path.split("/"))
        if any(part in ("", ".", "..") for part in parts):
            raise ContractError("path contiene componentes no permitidos")
        if parts[0] == _STAGING_DIRECTORY:
            raise ContractError("la ruta está reservada para el sistema de staging")
        return parts

    def _target(self, root: Path, path: str) -> Path:
        parts = self._path_parts(path)
        candidate = root
        for index, part in enumerate(parts):
            candidate = candidate / part
            try:
                metadata = candidate.lstat()
            except FileNotFoundError:
                if index < len(parts) - 1:
                    raise NotFoundError("el directorio padre no existe")
                return candidate
            if stat.S_ISLNK(metadata.st_mode):
                raise ContractError("no se permiten enlaces simbólicos en el destino")
            if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                raise ContractError("un componente intermedio no es directorio")
            if index == len(parts) - 1 and not stat.S_ISREG(metadata.st_mode):
                raise ContractError("el destino debe ser un archivo regular")
        return candidate

    @staticmethod
    def _hash_file(path: Path) -> str | None:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ContractError("el destino no es un archivo regular")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise ContractError("el destino no es un archivo regular")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest()
        finally:
            os.close(descriptor)

    def _staging_root(self, root: Path) -> Path:
        directory = root / _STAGING_DIRECTORY
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            metadata = directory.lstat()
        except OSError as exc:
            raise AtlasError("no se pudo preparar el área de staging") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ContractError("el área de staging no es un directorio seguro")
        return directory

    def _operation_directory(self, root: Path, operation_id: str) -> Path:
        directory = self._staging_root(root) / operation_id
        try:
            metadata = directory.lstat()
        except FileNotFoundError as exc:
            raise NotFoundError("operación de staging no encontrada") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ContractError("el registro de staging no es un directorio seguro")
        return directory

    @staticmethod
    def _write_manifest(directory: Path, manifest: dict) -> None:
        temporary = directory / ("manifest-" + uuid4().hex + ".tmp")
        final = directory / _MANIFEST_NAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, final)
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _read_manifest(self, directory: Path) -> dict:
        manifest_path = directory / _MANIFEST_NAME
        metadata = manifest_path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ContractError("manifest no es un archivo regular")
        raw = manifest_path.read_bytes()
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("manifest de staging corrupto") from exc
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
            raise ContractError("esquema de manifest de staging inválido")
        if manifest["schema_version"] != 1:
            raise ContractError("versión de manifest no soportada")
        if manifest["state"] not in {state.value for state in WorkspaceWriteState}:
            raise ContractError("estado de staging desconocido")
        if not isinstance(manifest["workspace_id"], str) or not manifest["workspace_id"].strip():
            raise ContractError("workspace_id inválido en manifest")
        if self._operation_id(manifest["operation_id"]) != manifest["operation_id"]:
            raise ContractError("operation_id inválido en manifest")
        self._path_parts(manifest["path"])
        if not isinstance(manifest["content_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", manifest["content_sha256"]
        ):
            raise ContractError("content_sha256 inválido en manifest")
        expected = manifest["expected_sha256"]
        if expected is not None and (
            not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
        ):
            raise ContractError("expected_sha256 inválido en manifest")
        if (
            isinstance(manifest["size_bytes"], bool)
            or not isinstance(manifest["size_bytes"], int)
            or manifest["size_bytes"] < 0
            or manifest["size_bytes"] > self._max_write_bytes
        ):
            raise ContractError("size_bytes inválido en manifest")
        return manifest

    @staticmethod
    def _stage_result(manifest: dict) -> WorkspaceWriteStage:
        return WorkspaceWriteStage(
            workspace_id=manifest["workspace_id"],
            operation_id=manifest["operation_id"],
            path=manifest["path"],
            content_sha256=manifest["content_sha256"],
            size_bytes=manifest["size_bytes"],
            expected_sha256=manifest["expected_sha256"],
        )

    def stage_write(
        self,
        workspace_id: str,
        path: str,
        content: str,
        operation_id: str,
        expected_sha256: str | None = None,
    ) -> WorkspaceWriteStage:
        root = self._root(workspace_id)
        operation_id = self._operation_id(operation_id)
        self._path_parts(path)
        if not isinstance(content, str):
            raise ContractError("content debe ser texto UTF-8")
        raw = content.encode("utf-8")
        if len(raw) > self._max_write_bytes:
            raise ContractError("el contenido supera el límite de escritura")
        if expected_sha256 is not None and (
            not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        ):
            raise ContractError("expected_sha256 debe ser SHA-256 hexadecimal")
        target = self._target(root, path)
        current_hash = self._hash_file(target)
        if current_hash != expected_sha256:
            raise ConcurrencyError("el destino no coincide con expected_sha256")
        content_hash = hashlib.sha256(raw).hexdigest()
        staging_root = self._staging_root(root)
        operation_dir = staging_root / operation_id

        if operation_dir.exists() or operation_dir.is_symlink():
            manifest = self._read_manifest(self._operation_directory(root, operation_id))
            expected_binding = (
                workspace_id, path, expected_sha256, content_hash, len(raw)
            )
            actual_binding = (
                manifest.get("workspace_id"), manifest.get("path"),
                manifest.get("expected_sha256"), manifest.get("content_sha256"),
                manifest.get("size_bytes"),
            )
            if manifest.get("operation_id") != operation_id or actual_binding != expected_binding:
                raise ConcurrencyError("operation_id ya está ligado a otra escritura")
            return self._stage_result(manifest)

        operation_dir.mkdir(mode=0o700)
        payload_path = operation_dir / "payload"
        descriptor = os.open(
            payload_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        manifest = {
            "schema_version": 1,
            "workspace_id": workspace_id,
            "operation_id": operation_id,
            "path": path,
            "expected_sha256": expected_sha256,
            "content_sha256": content_hash,
            "size_bytes": len(raw),
            "state": WorkspaceWriteState.STAGED.value,
        }
        self._write_manifest(operation_dir, manifest)
        root_fd = os.open(staging_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
        return self._stage_result(manifest)

    def _target_lock(self, root: Path, path: str):
        locks = self._staging_root(root) / "locks"
        locks.mkdir(mode=0o700, exist_ok=True)
        metadata = locks.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ContractError("el directorio de locks no es seguro")
        lock_name = hashlib.sha256(path.encode("utf-8")).hexdigest() + ".lock"
        lock_path = locks / lock_name
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    def commit_write(self, workspace_id: str, operation_id: str) -> WorkspaceWriteCommit:
        root = self._root(workspace_id)
        operation_id = self._operation_id(operation_id)
        operation_dir = self._operation_directory(root, operation_id)
        manifest = self._read_manifest(operation_dir)
        if manifest["workspace_id"] != workspace_id:
            raise NotFoundError("la operación no pertenece al workspace")
        if manifest["state"] == WorkspaceWriteState.COMMITTED.value:
            return WorkspaceWriteCommit(
                workspace_id, operation_id, manifest["path"],
                manifest["content_sha256"], manifest["size_bytes"], True,
            )
        target = self._target(root, manifest["path"])
        lock_fd = self._target_lock(root, manifest["path"])
        try:
            current_hash = self._hash_file(target)
            if current_hash == manifest["content_sha256"]:
                leftover_payload = operation_dir / "payload"
                if leftover_payload.exists():
                    leftover_payload.unlink()
                manifest["state"] = WorkspaceWriteState.COMMITTED.value
                self._write_manifest(operation_dir, manifest)
                return WorkspaceWriteCommit(
                    workspace_id, operation_id, manifest["path"],
                    manifest["content_sha256"], manifest["size_bytes"], True,
                )
            if current_hash != manifest["expected_sha256"]:
                raise ConcurrencyError("el destino cambió después del staging")
            payload = operation_dir / "payload"
            payload_hash = self._hash_file(payload)
            if payload_hash != manifest["content_sha256"]:
                raise ContractError("el payload de staging no coincide con su hash")
            manifest["state"] = WorkspaceWriteState.COMMITTING.value
            self._write_manifest(operation_dir, manifest)
            if manifest["expected_sha256"] is None:
                os.link(payload, target, follow_symlinks=False)
                payload.unlink()
            else:
                os.replace(payload, target)
            parent_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            manifest["state"] = WorkspaceWriteState.COMMITTED.value
            self._write_manifest(operation_dir, manifest)
        except FileExistsError as exc:
            raise ConcurrencyError("otro proceso creó el destino durante el commit") from exc
        except OSError as exc:
            raise AtlasError("falló el commit de la escritura; inspeccione recovery") from exc
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        return WorkspaceWriteCommit(
            workspace_id, operation_id, manifest["path"],
            manifest["content_sha256"], manifest["size_bytes"], True,
        )

    def assess_recovery(
        self, workspace_id: str, operation_id: str
    ) -> WorkspaceRecoveryAssessment:
        root = self._root(workspace_id)
        operation_id = self._operation_id(operation_id)
        try:
            operation_dir = self._operation_directory(root, operation_id)
            manifest = self._read_manifest(operation_dir)
            if manifest["workspace_id"] != workspace_id or manifest["operation_id"] != operation_id:
                return WorkspaceRecoveryAssessment(
                    workspace_id, operation_id, WorkspaceRecoveryStatus.CORRUPT,
                    detail="el binding del manifest no coincide",
                )
            target = self._target(root, manifest["path"])
            current_hash = self._hash_file(target)
            payload = operation_dir / "payload"
            payload_hash = self._hash_file(payload)
            state = manifest["state"]
            if state == WorkspaceWriteState.COMMITTED.value:
                status = WorkspaceRecoveryStatus.COMMITTED
            elif state == WorkspaceWriteState.STAGED.value:
                status = (
                    WorkspaceRecoveryStatus.STAGED_READY
                    if current_hash == manifest["expected_sha256"]
                    and payload_hash == manifest["content_sha256"]
                    else WorkspaceRecoveryStatus.CONFLICT
                )
            elif current_hash == manifest["content_sha256"]:
                status = WorkspaceRecoveryStatus.COMMIT_CONFIRMED
            elif (
                current_hash == manifest["expected_sha256"]
                and payload_hash == manifest["content_sha256"]
            ):
                status = WorkspaceRecoveryStatus.COMMIT_NOT_APPLIED
            else:
                status = WorkspaceRecoveryStatus.CONFLICT
            return WorkspaceRecoveryAssessment(
                workspace_id, operation_id, status, path=manifest["path"]
            )
        except NotFoundError:
            return WorkspaceRecoveryAssessment(
                workspace_id, operation_id, WorkspaceRecoveryStatus.CORRUPT,
                detail="no existe el registro durable de la operación",
            )
        except (OSError, KeyError, TypeError, ValueError, ContractError):
            return WorkspaceRecoveryAssessment(
                workspace_id, operation_id, WorkspaceRecoveryStatus.CORRUPT,
                detail="no se pudo verificar la integridad del staging",
            )
