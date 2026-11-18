"""Explicit offline entrypoint for the first Platform Admin bootstrap.

This command is intentionally separate from the conversational Atlas CLI and
is never imported by runtime or HTTP composition.
"""

import argparse
from pathlib import Path
import os
import sqlite3
import stat
import sys
from typing import Callable, Sequence

from atlas.adapters.sqlite import (
    SQLITE_MIGRATIONS,
    SQLiteDatabase,
    SQLiteIdentityAuthority,
)
from atlas.adapters.sqlite.platform_admin_bootstrap import (
    SQLitePlatformAdminBootstrapAdapter,
)
from atlas.adapters.system_clock import SystemClock
from atlas.application.platform_admin_bootstrap import PlatformAdminBootstrapService
from atlas.core.errors import AtlasError, AuthorizationError, ConcurrencyError
from atlas.core.identity import IdentityKind, IdentityStatus
from atlas.core.platform_admin import (
    INITIAL_PLATFORM_ADMIN_PERMISSIONS,
    PlatformAdminBootstrapRequest,
    PlatformAdminGrant,
)
from atlas.ports.platform_admin_authority import PlatformAdminBootstrapPort


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas-platform-admin-bootstrap",
        description="Bootstrap offline del primer Platform Admin (requiere TTY real).",
    )
    parser.add_argument("--database", required=True, help="ruta absoluta a una DB SQLite existente")
    parser.add_argument("--user-id", required=True, help="UUIDv4 del USER canónico destinatario")
    parser.add_argument(
        "--operation-id",
        required=True,
        help="UUIDv4 estable para permitir recuperación exacta tras una respuesta perdida",
    )
    return parser


def _require_tty(stdin, stdout) -> tuple[int, int, str]:
    if not callable(getattr(stdin, "isatty", None)) or not stdin.isatty():
        raise AuthorizationError("stdin debe estar conectado a una TTY real")
    if not callable(getattr(stdout, "isatty", None)) or not stdout.isatty():
        raise AuthorizationError("stdout debe estar conectado a una TTY real")
    try:
        terminal_id = os.ttyname(stdin.fileno())
        output_terminal_id = os.ttyname(stdout.fileno())
        real_uid = os.getuid()
        effective_uid = os.geteuid()
    except (AttributeError, OSError) as exc:
        raise AuthorizationError("no se pudo verificar la procedencia TTY/UID del proceso") from exc
    if (
        not isinstance(terminal_id, str)
        or not terminal_id.strip()
        or output_terminal_id != terminal_id
    ):
        raise AuthorizationError("stdin y stdout deben pertenecer a la misma TTY")
    return real_uid, effective_uid, terminal_id


def _validate_database_path(raw_path: str) -> Path:
    supplied = Path(raw_path).expanduser()
    if not supplied.is_absolute():
        raise AuthorizationError("--database debe ser una ruta absoluta")
    if supplied.is_symlink():
        raise AuthorizationError("--database no puede ser un enlace simbólico")
    try:
        resolved = supplied.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise AuthorizationError("la base de datos indicada no existe o no es accesible") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise AuthorizationError("--database debe apuntar a un archivo regular existente")
    return resolved


def _validate_schema_read_only(database_path: Path) -> int:
    """Verify the complete known migration ledger without creating or changing it."""
    uri = database_path.as_uri() + "?mode=ro"
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.Error as exc:
        raise AuthorizationError("no se pudo verificar el ledger SQLite en modo solo lectura") from exc
    finally:
        if connection is not None:
            connection.close()

    expected = SQLITE_MIGRATIONS
    if len(rows) != len(expected):
        raise AuthorizationError(
            f"schema no soportado: se requieren exactamente {len(expected)} migraciones aplicadas"
        )
    for row, migration in zip(rows, expected):
        if row != (migration.version, migration.name, migration.checksum):
            raise AuthorizationError(
                f"ledger de migraciones inválido o checksum distinto en V{migration.version}"
            )
    return expected[-1].version


def _print_grant(grant: PlatformAdminGrant, output_fn: Callable[[str], None]) -> None:
    output_fn("Bootstrap confirmado/persistido.")
    output_fn(f"grant_id: {grant.grant_id}")
    output_fn(f"user_id: {grant.user_id}")
    output_fn(f"status: {grant.status.value}")
    output_fn(f"revision: {grant.revision}")
    output_fn("permissions: " + ", ".join(sorted(item.value for item in grant.permissions)))
    output_fn(f"issued_at: {grant.issued_at.isoformat()}")
    output_fn(f"expires_at: {grant.expires_at.isoformat()}")


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    stdin=None,
    stdout=None,
) -> int:
    """Run the explicit, TTY-bound bootstrap command; never migrate the database."""
    parser = _parser()
    args = parser.parse_args(argv)
    selected_stdin = sys.stdin if stdin is None else stdin
    selected_stdout = sys.stdout if stdout is None else stdout

    try:
        real_uid, effective_uid, terminal_id = _require_tty(
            selected_stdin, selected_stdout
        )
        database_path = _validate_database_path(args.database)
        schema_version = _validate_schema_read_only(database_path)
        request = PlatformAdminBootstrapRequest(
            operation_id=args.operation_id,
            user_id=args.user_id,
            permissions=INITIAL_PLATFORM_ADMIN_PERMISSIONS,
        )

        database = SQLiteDatabase(database_path)
        bootstrap_port: PlatformAdminBootstrapPort = (
            SQLitePlatformAdminBootstrapAdapter(database)
        )

        # Exact committed retries are read-only and recover before consulting
        # current USER status or asking for a second confirmation.
        existing = bootstrap_port.get_operation(request.operation_id)
        if existing is not None:
            if (
                existing.request.user_id != request.user_id
                or existing.request.permissions != request.permissions
            ):
                raise ConcurrencyError(
                    "operation_id ya está asociado a otra intención de bootstrap"
                )
            output_fn("La operación indicada ya estaba confirmada; no se realizó otra escritura.")
            _print_grant(existing.grant, output_fn)
            return 0

        identity_authority = SQLiteIdentityAuthority(database)
        canonical = identity_authority.get_user(request.user_id)
        if canonical is None:
            raise AuthorizationError("el USER canónico solicitado no existe")
        if (
            canonical.identity.kind is not IdentityKind.USER
            or canonical.identity.status is not IdentityStatus.ACTIVE
        ):
            raise AuthorizationError("el USER canónico solicitado no está ACTIVE")

        output_fn("=== CONFIRMACIÓN DE BOOTSTRAP OFFLINE ===")
        output_fn(f"database: {database_path}")
        output_fn(f"schema_version: {schema_version}")
        output_fn(f"operation_id: {request.operation_id}")
        output_fn(f"user_id: {canonical.user_id}")
        output_fn(f"identity_id: {canonical.identity.identity_id}")
        output_fn(f"identity_kind: {canonical.identity.kind.value}")
        output_fn(f"identity_status: {canonical.identity.status.value}")
        output_fn(f"identity_revision: {canonical.identity.revision}")
        output_fn("permissions: association.suspend, association.reactivate")
        output_fn("grant_ttl: 90 days from confirmation")
        output_fn(f"operator_real_uid: {real_uid}")
        output_fn(f"operator_effective_uid: {effective_uid}")
        output_fn(f"terminal_id: {terminal_id}")
        expected_phrase = f"BOOTSTRAP PLATFORM ADMIN {canonical.user_id}"
        confirmation = input_fn("Escribe exactamente la frase de confirmación: ")
        if confirmation != expected_phrase:
            raise AuthorizationError("frase de confirmación incorrecta; no se escribió ningún grant")

        service = PlatformAdminBootstrapService(
            identity_authority=identity_authority,
            bootstrap_port=bootstrap_port,
            clock=SystemClock(),
        )
        grant = service.provision_first_admin(
            request,
            operator_real_uid=real_uid,
            operator_effective_uid=effective_uid,
            terminal_id=terminal_id,
        )
        _print_grant(grant, output_fn)
        return 0
    except (AtlasError, sqlite3.Error, OSError, ValueError) as exc:
        output_fn(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
