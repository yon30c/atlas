"""Atomic SQLite unit of work for Grants and renewal requests."""

from types import TracebackType
from typing import Self

from atlas.adapters.sqlite.database import SQLiteDatabase, SQLiteUnitOfWork
from atlas.adapters.sqlite.grant_repository import SQLiteGrantRepository
from atlas.adapters.sqlite.grant_renewal_repository import SQLiteGrantRenewalRepository
from atlas.core.errors import ContractError


class SQLiteAuthorizationUnitOfWork:
    """Shares one BEGIN IMMEDIATE transaction across Grants and renewals.

    A transaction is committed only when the application service explicitly
    calls commit(). Leaving the context without commit rolls it back.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database
        self._manager = None
        self._unit: SQLiteUnitOfWork | None = None
        self._connection = None
        self._active = False
        self._committed = False
        self.grants = None
        self.renewals = None

    def __enter__(self) -> Self:
        if self._active:
            raise ContractError("la unidad de autorización ya está activa")
        self._manager = self._database.unit_of_work()
        self._unit = self._manager.__enter__()
        self._connection = self._unit._connection_for(self._database)
        self._active = True
        self._committed = False
        self.grants = SQLiteGrantRepository(
            self._database,
            unit_of_work=self._unit,
        )
        self.renewals = SQLiteGrantRenewalRepository(
            self._database,
            unit_of_work=self._unit,
        )
        return self

    def commit(self) -> None:
        self._ensure_active()
        # The database context manager performs the physical commit on exit.
        # Keeping the transaction open allows a later exception to roll it back.
        self._committed = True

    def rollback(self) -> None:
        self._ensure_active()
        self._connection.rollback()
        self._committed = False

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._active or self._manager is None:
            return
        try:
            if exc_type is not None or not self._committed:
                self._connection.rollback()
            self._manager.__exit__(exc_type, exc_value, traceback)
        finally:
            self._active = False
            self._connection = None
            self._unit = None
            self._manager = None

    def _ensure_active(self) -> None:
        if (
            not self._active
            or self._connection is None
            or not self._connection.in_transaction
        ):
            raise ContractError("la unidad de autorización no está activa")


class SQLiteAuthorizationUnitOfWorkFactory:
    """Creates independent transaction scopes over one canonical database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if not isinstance(database, SQLiteDatabase):
            raise ContractError("database debe ser SQLiteDatabase")
        self._database = database

    def __call__(self) -> SQLiteAuthorizationUnitOfWork:
        return SQLiteAuthorizationUnitOfWork(self._database)
