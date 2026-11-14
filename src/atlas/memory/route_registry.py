"""Trusted delivery-route registry contract for protected Memory Engine reads.

This module defines neutral evidence only. It does not discover routes or
implement a runtime registry; consumer adapters must resolve routes from an
authoritative configuration source.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from atlas.core.errors import ContractError
from atlas.memory.consistency import DeliveryRouteSet


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive_int(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


class RouteRegistryStatus(str, Enum):
    RESOLVED = "resolved"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DeliveryRouteDescriptor:
    """Authoritative, non-secret description of one registered delivery route."""

    route_id: str
    revision: int
    enabled: bool
    supports_fencing: bool

    def __post_init__(self) -> None:
        _required(self.route_id, "route_id")
        _positive_int(self.revision, "revision")
        if not isinstance(self.enabled, bool):
            raise ContractError("enabled debe ser bool")
        if not isinstance(self.supports_fencing, bool):
            raise ContractError("supports_fencing debe ser bool")

    @property
    def usable_for_protected_delivery(self) -> bool:
        """A route is usable only while enabled and able to enforce fencing."""
        return self.enabled and self.supports_fencing


@dataclass(frozen=True, slots=True)
class RouteRegistryResult:
    """All-or-nothing resolution of the exact route IDs requested by a caller."""

    requested_route_ids: frozenset[str]
    status: RouteRegistryStatus
    routes: tuple[DeliveryRouteDescriptor, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.requested_route_ids, frozenset) or not self.requested_route_ids:
            raise ContractError("requested_route_ids debe ser un frozenset no vacío")
        for route_id in self.requested_route_ids:
            _required(route_id, "requested_route_id")
        if not isinstance(self.status, RouteRegistryStatus):
            raise ContractError("status debe ser RouteRegistryStatus")
        if not isinstance(self.routes, tuple):
            raise ContractError("routes debe ser tuple")
        if any(not isinstance(route, DeliveryRouteDescriptor) for route in self.routes):
            raise ContractError("routes solo puede contener DeliveryRouteDescriptor")

        resolved_ids = tuple(route.route_id for route in self.routes)
        if len(resolved_ids) != len(set(resolved_ids)):
            raise ContractError("el registro devolvió rutas duplicadas")
        if self.status is RouteRegistryStatus.RESOLVED:
            if frozenset(resolved_ids) != self.requested_route_ids:
                raise ContractError("RESOLVED requiere resolver exactamente todas las rutas solicitadas")
        elif self.routes:
            raise ContractError("REJECTED/UNAVAILABLE no pueden devolver rutas parciales")

    @property
    def usable_for_protected_delivery(self) -> bool:
        """True only for a complete resolution whose every route supports fencing."""
        return (
            self.status is RouteRegistryStatus.RESOLVED
            and len(self.routes) == len(self.requested_route_ids)
            and all(route.usable_for_protected_delivery for route in self.routes)
        )


class DeliveryRouteRegistryPort(Protocol):
    """Resolve route IDs against trusted configuration, never caller assertions.

    Implementations must return RESOLVED only for an exact, complete match.
    Unknown, partially registered, malformed or ambiguous route sets are
    REJECTED; unavailable configuration is UNAVAILABLE. Both outcomes deny
    admission. Route enable/disable/replacement changes must be ordered through
    the same invalidation/fencing authority before they become effective.
    """

    def resolve_routes(self, routes: DeliveryRouteSet) -> RouteRegistryResult:
        """Resolve every route ID or fail closed without returning partial data."""
