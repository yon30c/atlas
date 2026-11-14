"""Local immutable filesystem store for checkpoint projection artifacts.

This adapter is intentionally independent of the SQLite journal. It provides
content addressing and crash-safe publication, not an external anti-rollback
anchor. Its configured root must be provisioned and protected separately from
the journal database by the application owner.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import tempfile

from atlas.core.errors import ContractError
from atlas.memory.checkpoint_projection_codec import (
    CheckpointProjectionArtifacts,
    decode_checkpoint_projection_artifacts,
)
from atlas.ports.local_consistency_recovery import (
    CheckpointProjectionResolution,
    LocalCheckpointProjectionRequest,
    LocalVerificationStatus,
    VerifiedCheckpointProjection,
)
from atlas.ports.checkpoint_projection_store import (
    LocalCheckpointProjectionPublisherPort,
)


_REFERENCE = re.compile(r"^sha256:([0-9a-f]{64})$")


class FilesystemCheckpointProjectionStore(
    LocalCheckpointProjectionPublisherPort
):
    """Publish and resolve immutable SHA-256-addressed projection objects."""

    def __init__(self, root: str | Path) -> None:
        configured = Path(root)
        if not configured.is_absolute():
            raise ContractError("la raíz del almacén debe ser una ruta absoluta")
        try:
            resolved = configured.resolve(strict=True)
        except OSError as exc:
            raise ContractError("la raíz del almacén debe existir") from exc
        if resolved != configured or not configured.is_dir():
            raise ContractError("la raíz debe ser un directorio real sin symlinks")
        self._root = configured
        self._state_dir = self._prepare_directory("state")
        self._manifest_dir = self._prepare_directory("integrity")

    def _prepare_directory(self, name: str) -> Path:
        path = self._root / name
        try:
            path.mkdir(mode=0o700, exist_ok=True)
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise ContractError(f"directorio de almacén inválido: {name}")
            mode = stat.S_IMODE(metadata.st_mode)
            if (mode & 0o077) != 0 or (mode & 0o700) != 0o700:
                raise ContractError(
                    f"directorio de almacén debe tener permisos 0700: {name}"
                )
            resolved = path.resolve(strict=True)
            if resolved != path:
                raise ContractError(f"directorio de almacén no canónico: {name}")
            self._fsync_directory(self._root)
            return path
        except OSError as exc:
            raise ContractError(f"no se pudo preparar el almacén: {name}") from exc

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _digest_from_reference(reference: str) -> str:
        if not isinstance(reference, str):
            raise ContractError("referencia de objeto inválida")
        match = _REFERENCE.fullmatch(reference)
        if match is None:
            raise ContractError("referencia debe ser SHA-256 content-addressed")
        return match.group(1)

    def _path_for(self, directory: Path, reference: str) -> Path:
        return directory / self._digest_from_reference(reference)

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ContractError("el objeto almacenado no es un archivo regular")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def _publish_immutable(self, directory: Path, reference: str, raw: bytes) -> None:
        if not isinstance(raw, bytes):
            raise ContractError("el contenido del objeto debe ser bytes")
        destination = self._path_for(directory, reference)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".pending-", dir=directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError:
                existing = self._read_file(destination)
                if existing != raw:
                    raise ContractError(
                        "colisión o corrupción: objeto existente difiere"
                    )
            temporary.unlink(missing_ok=True)
            self._fsync_directory(directory)
            if self._read_file(destination) != raw:
                raise ContractError("read-back del objeto publicado no coincide")
        finally:
            temporary.unlink(missing_ok=True)

    def publish_checkpoint_projection(
        self, artifacts: CheckpointProjectionArtifacts
    ) -> None:
        """Publish state then manifest; an orphan state blob is harmless."""
        if not isinstance(artifacts, CheckpointProjectionArtifacts):
            raise ContractError("artifacts debe ser CheckpointProjectionArtifacts")
        decode_checkpoint_projection_artifacts(
            artifacts.state_bytes,
            artifacts.manifest_bytes,
            expected_state_reference=artifacts.state_reference,
            expected_integrity_reference=artifacts.integrity_reference,
        )
        self._publish_immutable(
            self._state_dir, artifacts.state_reference, artifacts.state_bytes
        )
        self._publish_immutable(
            self._manifest_dir,
            artifacts.integrity_reference,
            artifacts.manifest_bytes,
        )
        # Verify the pair from the durable paths, not from the caller's buffers.
        decode_checkpoint_projection_artifacts(
            self._read_file(self._path_for(self._state_dir, artifacts.state_reference)),
            self._read_file(self._path_for(self._manifest_dir, artifacts.integrity_reference)),
            expected_state_reference=artifacts.state_reference,
            expected_integrity_reference=artifacts.integrity_reference,
        )

    def resolve_checkpoint_projection(
        self, request: LocalCheckpointProjectionRequest
    ) -> CheckpointProjectionResolution:
        """Resolve exact checkpoint references; fail closed on missing/corrupt data."""
        if not isinstance(request, LocalCheckpointProjectionRequest):
            return CheckpointProjectionResolution(LocalVerificationStatus.REJECTED)
        try:
            state_path = self._path_for(
                self._state_dir, request.checkpoint.state_reference
            )
            manifest_path = self._path_for(
                self._manifest_dir, request.checkpoint.integrity_reference
            )
            state_bytes = self._read_file(state_path)
            manifest_bytes = self._read_file(manifest_path)
        except FileNotFoundError:
            return CheckpointProjectionResolution(LocalVerificationStatus.UNAVAILABLE)
        except PermissionError:
            return CheckpointProjectionResolution(LocalVerificationStatus.UNAVAILABLE)
        except OSError:
            return CheckpointProjectionResolution(LocalVerificationStatus.UNAVAILABLE)
        except ContractError:
            return CheckpointProjectionResolution(LocalVerificationStatus.REJECTED)

        try:
            projection, manifest, integrity_commitment = (
                decode_checkpoint_projection_artifacts(
                    state_bytes,
                    manifest_bytes,
                    expected_state_reference=request.checkpoint.state_reference,
                    expected_integrity_reference=request.checkpoint.integrity_reference,
                )
            )
            if (
                manifest.checkpoint_id != request.checkpoint.checkpoint_id
                or manifest.consistency_domain_id != request.consistency_domain_id
                or manifest.authority_epoch != request.authority_epoch
                or manifest.sequence != request.checkpoint.position.sequence
                or manifest.trust_policy_version != request.trust_policy_version
                or manifest.schema_version not in request.allowed_schema_versions
                or manifest.reducer_version not in request.allowed_reducer_versions
            ):
                return CheckpointProjectionResolution(LocalVerificationStatus.REJECTED)

            evidence = VerifiedCheckpointProjection(
                checkpoint_id=manifest.checkpoint_id,
                consistency_domain_id=manifest.consistency_domain_id,
                authority_epoch=manifest.authority_epoch,
                sequence=manifest.sequence,
                state_reference=manifest.state_reference,
                integrity_reference=request.checkpoint.integrity_reference,
                state_commitment=manifest.state_commitment,
                integrity_commitment=integrity_commitment,
                schema_version=manifest.schema_version,
                reducer_version=manifest.reducer_version,
                trust_policy_version=manifest.trust_policy_version,
                projection=projection,
                verification_id=(
                    f"local-filesystem-checkpoint:{manifest.checkpoint_id}:"
                    f"{integrity_commitment}"
                ),
            )
            return CheckpointProjectionResolution(
                LocalVerificationStatus.VERIFIED, evidence
            )
        except ContractError:
            return CheckpointProjectionResolution(LocalVerificationStatus.REJECTED)
        except Exception:
            return CheckpointProjectionResolution(LocalVerificationStatus.REJECTED)
