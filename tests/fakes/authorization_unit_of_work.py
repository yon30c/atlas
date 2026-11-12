
"""Adaptadores en memoria para probar transacciones de autorización."""
from threading import RLock

from atlas.authorization.models import Grant, GrantRenewalRequest
from atlas.core.errors import ConcurrencyError, ContractError


def _validate_expected_version(expected_version: int) -> None:
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise ContractError(
            "expected_version debe ser un entero positivo"
        )


class InMemoryGrantRepository:
    def __init__(self) -> None:
        self.grants: dict[str, Grant] = {}
        self.update_calls = 0
        self._lock = RLock()

    def create(self, grant: Grant) -> None:
        with self._lock:
            if grant.grant_id in self.grants:
                raise ContractError("El grant_id ya existe")
            self.grants[grant.grant_id] = grant

    def get(self, grant_id: str) -> Grant | None:
        with self._lock:
            return self.grants.get(grant_id)

    def update(self, grant: Grant) -> None:
        with self._lock:
            self.update_calls += 1
            self.grants[grant.grant_id] = grant

    def list_by_owner(self, owner_user_id: str) -> tuple[Grant, ...]:
        with self._lock:
            return tuple(
                grant
                for grant in self.grants.values()
                if grant.owner_user_id == owner_user_id
            )


class InMemoryRenewalRepository:
    def __init__(self) -> None:
        self.requests: dict[str, GrantRenewalRequest] = {}
        self.fail_on_update = False
        self._lock = RLock()

    def create(self, request: GrantRenewalRequest) -> None:
        with self._lock:
            if request.renewal_id in self.requests:
                raise ContractError("El renewal_id ya existe")
            self.requests[request.renewal_id] = request

    def get(self, renewal_id: str) -> GrantRenewalRequest | None:
        with self._lock:
            return self.requests.get(renewal_id)

    def update(self, request: GrantRenewalRequest) -> None:
        with self._lock:
            if self.fail_on_update:
                raise RuntimeError(
                    "Fallo simulado al actualizar la renovación"
                )
            self.requests[request.renewal_id] = request

    def update_if_version(
        self,
        request: GrantRenewalRequest,
        expected_version: int,
    ) -> bool:
        _validate_expected_version(expected_version)

        with self._lock:
            if self.fail_on_update:
                raise RuntimeError(
                    "Fallo simulado al actualizar la renovación"
                )

            current = self.requests.get(request.renewal_id)
            if current is None or current.version != expected_version:
                return False

            if request.version != expected_version + 1:
                raise ContractError(
                    "La nueva versión debe ser expected_version + 1"
                )

            self.requests[request.renewal_id] = request
            return True

    def list_by_grant(
        self,
        grant_id: str,
    ) -> tuple[GrantRenewalRequest, ...]:
        with self._lock:
            return tuple(
                request
                for request in self.requests.values()
                if request.grant_id == grant_id
            )


class _UnitOfWorkGrantRepository:
    """Repositorio con escrituras aisladas para una transacción."""

    def __init__(
        self,
        shared: InMemoryGrantRepository,
        uow: "InMemoryAuthorizationUnitOfWork",
    ) -> None:
        self._shared = shared
        self._uow = uow

    def create(self, grant: Grant) -> None:
        self._uow._ensure_active()

        if self.get(grant.grant_id) is not None:
            raise ContractError("El grant_id ya existe")

        self._uow._grant_creates.add(grant.grant_id)
        self._uow._grant_writes[grant.grant_id] = grant

    def get(self, grant_id: str) -> Grant | None:
        self._uow._ensure_active()

        if grant_id in self._uow._grant_writes:
            return self._uow._grant_writes[grant_id]

        with self._uow._lock:
            return self._shared.grants.get(grant_id)

    def update(self, grant: Grant) -> None:
        self._uow._ensure_active()
        self._shared.update_calls += 1
        self._uow._grant_writes[grant.grant_id] = grant

    def list_by_owner(self, owner_user_id: str) -> tuple[Grant, ...]:
        self._uow._ensure_active()

        with self._uow._lock:
            results = dict(self._shared.grants)

        results.update(self._uow._grant_writes)

        return tuple(
            grant
            for grant in results.values()
            if grant.owner_user_id == owner_user_id
        )


class _UnitOfWorkRenewalRepository:
    """Repositorio de renovaciones con control de versiones."""

    def __init__(
        self,
        shared: InMemoryRenewalRepository,
        uow: "InMemoryAuthorizationUnitOfWork",
    ) -> None:
        self._shared = shared
        self._uow = uow

    def create(self, request: GrantRenewalRequest) -> None:
        self._uow._ensure_active()

        if self.get(request.renewal_id) is not None:
            raise ContractError("El renewal_id ya existe")

        self._uow._renewal_creates.add(request.renewal_id)
        self._uow._renewal_writes[request.renewal_id] = request

    def get(self, renewal_id: str) -> GrantRenewalRequest | None:
        self._uow._ensure_active()

        if renewal_id in self._uow._renewal_writes:
            return self._uow._renewal_writes[renewal_id]

        with self._uow._lock:
            return self._shared.requests.get(renewal_id)

    def update(self, request: GrantRenewalRequest) -> None:
        self._uow._ensure_active()

        if self._shared.fail_on_update:
            raise RuntimeError(
                "Fallo simulado al actualizar la renovación"
            )

        self._uow._renewal_writes[request.renewal_id] = request

    def update_if_version(
        self,
        request: GrantRenewalRequest,
        expected_version: int,
    ) -> bool:
        self._uow._ensure_active()
        _validate_expected_version(expected_version)

        if self._shared.fail_on_update:
            raise RuntimeError(
                "Fallo simulado al actualizar la renovación"
            )

        with self._uow._lock:
            current = self._shared.requests.get(request.renewal_id)

            if current is None or current.version != expected_version:
                return False

            if request.version != expected_version + 1:
                raise ContractError(
                    "La nueva versión debe ser expected_version + 1"
                )

            previous_expected = (
                self._uow._renewal_cas.get(request.renewal_id)
            )

            if (
                previous_expected is not None
                and previous_expected != expected_version
            ):
                return False

            self._uow._renewal_cas[request.renewal_id] = expected_version
            self._uow._renewal_writes[request.renewal_id] = request

            return True

    def list_by_grant(
        self,
        grant_id: str,
    ) -> tuple[GrantRenewalRequest, ...]:
        self._uow._ensure_active()

        with self._uow._lock:
            results = dict(self._shared.requests)

        results.update(self._uow._renewal_writes)

        return tuple(
            request
            for request in results.values()
            if request.grant_id == grant_id
        )


class InMemoryAuthorizationUnitOfWork:
    def __init__(
        self,
        grants: InMemoryGrantRepository,
        renewals: InMemoryRenewalRepository,
        lock: RLock,
    ) -> None:
        self._shared_grants = grants
        self._shared_renewals = renewals
        self._lock = lock

        self._grant_writes: dict[str, Grant] = {}
        self._renewal_writes: dict[str, GrantRenewalRequest] = {}

        self._grant_creates: set[str] = set()
        self._renewal_creates: set[str] = set()

        self._renewal_cas: dict[str, int] = {}

        self._active = False
        self._committed = False

        self.grants = _UnitOfWorkGrantRepository(grants, self)
        self.renewals = _UnitOfWorkRenewalRepository(renewals, self)

    def __enter__(self) -> "InMemoryAuthorizationUnitOfWork":
        if self._active:
            raise RuntimeError("La unidad de trabajo ya está activa")

        self._active = True
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        if not self._active:
            return

        if exc_type is not None or not self._committed:
            self.rollback()
            return

        self._clear()
        self._active = False

    def commit(self) -> None:
        self._ensure_active()

        with self._lock:
            # 1. Validar concurrencia antes de preparar los cambios.
            for renewal_id, expected_version in self._renewal_cas.items():
                current = self._shared_renewals.requests.get(renewal_id)

                if (
                    current is None
                    or current.version != expected_version
                ):
                    raise ConcurrencyError(
                        "La solicitud cambió antes de confirmar la transacción"
                    )

            # 2. Validar unicidad de los nuevos registros.
            for grant_id in self._grant_creates:
                if grant_id in self._shared_grants.grants:
                    raise ContractError("El grant_id ya existe")

            for renewal_id in self._renewal_creates:
                if renewal_id in self._shared_renewals.requests:
                    raise ContractError("El renewal_id ya existe")

            # 3. Preparar ambos estados sin modificar los compartidos.
            next_grants = dict(self._shared_grants.grants)
            next_renewals = dict(self._shared_renewals.requests)
            next_grants.update(self._grant_writes)
            next_renewals.update(self._renewal_writes)

            # 4. Publicar los estados preparados.
            self._shared_grants.grants = next_grants
            self._shared_renewals.requests = next_renewals
        self._committed = True

    def rollback(self) -> None:
        self._ensure_active()
        self._clear()
        self._active = False
        self._committed = False

    def _ensure_active(self) -> None:
        if not self._active:
            raise RuntimeError("La unidad de trabajo no está activa")

    def _clear(self) -> None:
        self._grant_writes.clear()
        self._renewal_writes.clear()
        self._grant_creates.clear()
        self._renewal_creates.clear()
        self._renewal_cas.clear()


class InMemoryAuthorizationUnitOfWorkFactory:
    def __init__(
        self,
        grants: InMemoryGrantRepository | None = None,
        renewals: InMemoryRenewalRepository | None = None,
    ) -> None:
        self._lock = RLock()

        self.grants = (
            grants if grants is not None else InMemoryGrantRepository()
        )
        self.renewals = (
            renewals if renewals is not None else InMemoryRenewalRepository()
        )

        # Ambos repositorios comparten el mismo bloqueo transaccional.
        self.grants._lock = self._lock
        self.renewals._lock = self._lock

    def __call__(self) -> InMemoryAuthorizationUnitOfWork:
        return InMemoryAuthorizationUnitOfWork(
            self.grants,
            self.renewals,
            self._lock,
        )
