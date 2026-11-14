"""SQLite connection, transaction and immutable migration foundation.

This module deliberately does not implement Atlas journal or authority ports.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from threading import local
from typing import Iterator, Sequence

from atlas.core.errors import ContractError


@dataclass(frozen=True, slots=True)
class SQLiteMigration:
    """Immutable, checksummed schema migration."""

    version: int
    name: str
    sql: str

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ContractError("migration version debe ser un entero positivo")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ContractError("migration name debe ser no vacío")
        if not isinstance(self.sql, str) or not self.sql.strip():
            raise ContractError("migration sql debe ser no vacío")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


class SQLiteUnitOfWork:
    """Active transaction handle owned by exactly one SQLiteDatabase.

    The underlying connection is intentionally exposed only through the
    database-private ownership check used by infrastructure adapters.
    """

    __slots__ = ("_owner", "_connection", "_active")

    def __init__(
        self,
        owner: "SQLiteDatabase",
        connection: sqlite3.Connection,
    ) -> None:
        self._owner = owner
        self._connection = connection
        self._active = True

    def _connection_for(self, owner: "SQLiteDatabase") -> sqlite3.Connection:
        """Return the connection only to the exact owning database while active."""
        if owner is not self._owner:
            raise ContractError("SQLiteUnitOfWork pertenece a otra instancia de base de datos")
        if not self._active or not self._connection.in_transaction:
            raise ContractError("SQLiteUnitOfWork ya no está activa")
        return self._connection

    def _deactivate(self) -> None:
        self._active = False


class SQLiteDatabase:
    """File-backed SQLite database configured for durable local transactions.

    A new connection is opened per operation so independent processes and
    threads do not share a Python connection object.
    """

    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        if isinstance(path, str) and not path.strip():
            raise ContractError("database path debe ser no vacío")
        try:
            resolved = Path(path).expanduser()
        except (TypeError, ValueError) as exc:
            raise ContractError("database path inválido") from exc
        if str(path) == ":memory:" or not resolved.is_absolute():
            raise ContractError("SQLite requiere una ruta absoluta a archivo; :memory: no está permitido")
        if not resolved.parent.exists() or not resolved.parent.is_dir():
            raise ContractError("el directorio padre de SQLite debe existir")
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int) or busy_timeout_ms < 0:
            raise ContractError("busy_timeout_ms debe ser un entero no negativo")
        self._path = resolved
        self._busy_timeout_ms = busy_timeout_ms
        self._transaction_state = local()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def busy_timeout_ms(self) -> int:
        return self._busy_timeout_ms

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self._path),
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        if foreign_keys != 1 or synchronous != 2 or busy_timeout != self._busy_timeout_ms:
            connection.close()
            raise sqlite3.DatabaseError("SQLite no pudo aplicar la configuración de seguridad requerida")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and always close it."""
        connection = self._open()
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Enable WAL and create the migration ledger without applying schema changes."""
        with self.connection() as connection:
            mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if not isinstance(mode, str) or mode.lower() != "wal":
                raise sqlite3.DatabaseError("SQLite no confirmó journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY CHECK (version > 0),
                        name TEXT NOT NULL,
                        checksum TEXT NOT NULL CHECK (length(checksum) = 64),
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _execute_statements(connection: sqlite3.Connection, sql: str) -> None:
        """Execute a SQL script statement-by-statement without executescript's implicit commit."""
        statement = ""
        for character in sql:
            statement += character
            if character == ";" and sqlite3.complete_statement(statement):
                if statement.strip():
                    connection.execute(statement)
                statement = ""
        if statement.strip():
            if not sqlite3.complete_statement(statement):
                raise ContractError("migration contiene una sentencia SQL incompleta")
            connection.execute(statement)

    def apply_migrations(self, migrations: Sequence[SQLiteMigration]) -> int:
        """Apply a complete, ordered migration history with checksum verification."""
        if not isinstance(migrations, (tuple, list)):
            raise ContractError("migrations debe ser tuple o list")
        if any(not isinstance(item, SQLiteMigration) for item in migrations):
            raise ContractError("migrations solo puede contener SQLiteMigration")
        ordered = tuple(sorted(migrations, key=lambda item: item.version))
        versions = tuple(item.version for item in ordered)
        if len(versions) != len(set(versions)):
            raise ContractError("migration versions duplicadas")
        if versions and versions != tuple(range(1, versions[-1] + 1)):
            raise ContractError("migration history debe ser completa y consecutiva")

        self.initialize()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                applied_rows = connection.execute(
                    "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
                applied = {row["version"]: row for row in applied_rows}
                if tuple(applied) != tuple(range(1, len(applied) + 1)):
                    raise sqlite3.DatabaseError("ledger de migraciones tiene versiones discontinuas")
                if len(applied) > len(ordered):
                    raise sqlite3.DatabaseError("faltan migraciones históricas en el código")
                for migration in ordered:
                    previous = applied.get(migration.version)
                    if previous is not None:
                        if (
                            previous["name"] != migration.name
                            or previous["checksum"] != migration.checksum
                        ):
                            raise sqlite3.DatabaseError(
                                f"checksum/nombre de migración alterado: {migration.version}"
                            )
                        continue
                    if migration.version != len(applied) + 1:
                        raise sqlite3.DatabaseError("migración fuera de secuencia")
                    self._execute_statements(connection, migration.sql)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations(version, name, checksum, applied_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            migration.version,
                            migration.name,
                            migration.checksum,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    applied[migration.version] = {
                        "version": migration.version,
                        "name": migration.name,
                        "checksum": migration.checksum,
                    }
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return len(ordered)

    @contextmanager
    def unit_of_work(self) -> Iterator[SQLiteUnitOfWork]:
        """Open one owned BEGIN IMMEDIATE transaction for composed local mutations.

        The context manager alone controls commit, rollback and connection
        lifetime. A unit of work cannot be nested on the same thread or reused
        after its context has exited.
        """
        if getattr(self._transaction_state, "active", False):
            raise ContractError("SQLiteUnitOfWork anidada no está permitida")
        self._transaction_state.active = True
        connection = None
        unit = None
        try:
            connection = self._open()
            connection.execute("BEGIN IMMEDIATE")
            unit = SQLiteUnitOfWork(self, connection)
            try:
                yield unit
            except BaseException:
                connection.rollback()
                raise
            else:
                try:
                    connection.commit()
                except BaseException:
                    try:
                        connection.rollback()
                    except sqlite3.Error:
                        pass
                    raise
        finally:
            if unit is not None:
                unit._deactivate()
            if connection is not None:
                connection.close()
            self._transaction_state.active = False

    @contextmanager
    def write_transaction(self) -> Iterator[sqlite3.Connection]:
        """Compatibility wrapper yielding the legacy raw connection API."""
        with self.unit_of_work() as unit:
            yield unit._connection_for(self)
