"""Dedicated interactive Linux entrypoint for offline association provisioning.

Run explicitly with sudo:
    sudo python -m atlas.adapters.sqlite.offline_association_provisioning_cli \
        --database /absolute/path/to/atlas.sqlite --operation-id <uuid4>

This module is deliberately not registered as an application/runtime command.
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
from uuid import UUID, uuid4

from atlas.adapters.sqlite.authentication_attempt_migration import CORE_SCHEMA_V28
from atlas.adapters.sqlite.database import SQLiteDatabase
from atlas.adapters.sqlite.migrations import SQLITE_MIGRATIONS
from atlas.adapters.sqlite.project_environment_association_provisioning_writer import (
    SQLiteProjectEnvironmentAssociationProvisioningWriter,
)
from atlas.adapters.sqlite.project_environment_association_repository import (
    SQLiteProjectEnvironmentAssociationRepository,
)
from atlas.adapters.sqlite.project_environment_repository import SQLiteProjectEnvironmentRepository
from atlas.core.errors import AtlasError, ContractError
from atlas.core.project_environment_association_provisioning import (
    ProjectEnvironmentAssociationProvisioningProvenance,
    ProjectEnvironmentAssociationProvisioningRequest,
)
from atlas.memory.models import EnvironmentId, ProjectId


def _require_sudo_tty() -> tuple[int, int, str]:
    if not sys.platform.startswith("linux") or not hasattr(os, "getuid"):
        raise PermissionError("el aprovisionamiento solo está disponible en Linux")
    real_uid = os.getuid()
    effective_uid = os.geteuid()
    if real_uid <= 0 or effective_uid != 0:
        raise PermissionError("ejecute mediante sudo: UID real no-root y UID efectivo 0 requeridos")
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid is None or not sudo_uid.isdigit() or int(sudo_uid) != real_uid:
        raise PermissionError("la identidad real no coincide con SUDO_UID")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PermissionError("se requiere una terminal interactiva; no se permiten pipes")
    try:
        input_tty = os.ttyname(sys.stdin.fileno())
        output_tty = os.ttyname(sys.stdout.fileno())
    except OSError as exc:
        raise PermissionError("no se pudo verificar la terminal interactiva") from exc
    if input_tty != output_tty:
        raise PermissionError("entrada y salida deben pertenecer a la misma terminal")
    try:
        foreground_group = os.tcgetpgrp(sys.stdin.fileno())
    except (AttributeError, OSError) as exc:
        raise PermissionError("no se pudo verificar el primer plano de la terminal") from exc
    if foreground_group != os.getpgrp():
        raise PermissionError("el comando debe ejecutarse en primer plano de la terminal")
    return real_uid, effective_uid, input_tty


def _require_current_schema(database: SQLiteDatabase) -> None:
    expected = tuple(
        (migration.version, migration.name, migration.checksum)
        for migration in SQLITE_MIGRATIONS
    )
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    actual = tuple((row["version"], row["name"], row["checksum"]) for row in rows)
    if actual != expected or not expected or expected[-1][0] != CORE_SCHEMA_V28.version:
        raise ContractError("la base no tiene exactamente el historial de migraciones esperado hasta V28")


def _parse_operation_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("operation-id debe ser UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise argparse.ArgumentTypeError("operation-id debe ser UUIDv4 canónico")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aprovisionamiento offline y auditado de una asociación Project/Environment."
    )
    parser.add_argument("--database", required=True, help="ruta absoluta a la base SQLite existente")
    parser.add_argument("--operation-id", required=True, type=_parse_operation_id)
    args = parser.parse_args(argv)

    try:
        real_uid, effective_uid, terminal_id = _require_sudo_tty()
        database_path = Path(args.database).expanduser()
        if not database_path.is_absolute() or database_path.is_symlink() or not database_path.is_file():
            raise ContractError("database debe ser un archivo SQLite existente, absoluto y no symlink")
        database = SQLiteDatabase(database_path)
        _require_current_schema(database)

        project_id = input("Project ID: ").strip()
        environment_id = input("Environment ID: ").strip()
        if not project_id or not environment_id:
            raise ContractError("Project ID y Environment ID son obligatorios")

        projects = SQLiteProjectEnvironmentRepository(database)
        if projects.get_project(ProjectId(project_id)) is None:
            raise ContractError("Project canónico inexistente")
        if projects.get_environment(EnvironmentId(environment_id)) is None:
            raise ContractError("Environment canónico inexistente")

        reader = SQLiteProjectEnvironmentAssociationRepository(database)
        if reader.get_association(ProjectId(project_id), EnvironmentId(environment_id)) is not None:
            raise ContractError("la asociación Project/Environment ya existe")

        reason = input("Motivo obligatorio (1-500 caracteres): ").strip()
        if not reason or len(reason) > 500 or any(ord(char) < 32 or ord(char) == 127 for char in reason):
            raise ContractError("motivo inválido: use entre 1 y 500 caracteres sin controles")

        confirmation = f"CONFIRM PROJECT={project_id} ENVIRONMENT={environment_id}"
        print(f"Para confirmar, escriba exactamente: {confirmation}")
        if input("> ") != confirmation:
            raise PermissionError("confirmación exacta no coincidente; operación cancelada")

        request = ProjectEnvironmentAssociationProvisioningRequest(
            operation_id=args.operation_id,
            project_id=ProjectId(project_id),
            environment_id=EnvironmentId(environment_id),
            reason=reason,
        )
        provenance = ProjectEnvironmentAssociationProvisioningProvenance(
            event_id=str(uuid4()),
            real_uid=real_uid,
            effective_uid=effective_uid,
            terminal_id=terminal_id,
            occurred_at=datetime.now(timezone.utc),
        )
        writer = SQLiteProjectEnvironmentAssociationProvisioningWriter(database)
        writer.create_association(request, provenance)
        print(
            "Aprovisionamiento registrado: "
            f"project={project_id} environment={environment_id} "
            f"operation_id={args.operation_id}"
        )
        return 0
    except (AtlasError, PermissionError, OSError, sqlite3.Error, ValueError, EOFError) as exc:
        print(f"Aprovisionamiento denegado: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
