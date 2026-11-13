"""Modelos puros del cierre lógico de Forget (ME-03).

Estos modelos representan únicamente el cierre de admisiones y la supresión
lógica. No representan eliminación física ni el estado MemoryVersion.FORGOTTEN.
"""
from dataclasses import dataclass
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.identifiers import validate_atlas_id
from atlas.memory.consistency import ReadAdmission, ReadAdmissionStatus


def _required(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} debe ser una cadena no vacía")


def _positive_int(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{field} debe ser un entero positivo")


class ForgetClosureStatus(str, Enum):
    CLOSING = "closing"
    SUPPRESSED = "suppressed"


@dataclass(frozen=True, slots=True)
class ForgetTarget:
    """Forget v1 cubre la memoria lógica completa y todas sus versiones."""

    memory_id: str

    def __post_init__(self) -> None:
        validate_atlas_id(self.memory_id, "memory_id")


@dataclass(frozen=True, slots=True)
class ForgetClosure:
    """Evidencia mínima de cierre; nunca contiene payload ni hashes."""

    closure_id: str
    operation_id: str
    idempotency_key: str
    target: ForgetTarget
    generation: int
    affected_admission_ids: frozenset[str]
    unresolved_admission_ids: frozenset[str]
    delivery_route_ids: frozenset[str]
    status: ForgetClosureStatus

    def __post_init__(self) -> None:
        for field in ("closure_id", "operation_id", "idempotency_key"):
            _required(getattr(self, field), field)
        validate_atlas_id(self.closure_id, "closure_id")
        if not isinstance(self.target, ForgetTarget):
            raise ContractError("target debe ser ForgetTarget")
        _positive_int(self.generation, "generation")
        for field in (
            "affected_admission_ids",
            "unresolved_admission_ids",
            "delivery_route_ids",
        ):
            values = getattr(self, field)
            if not isinstance(values, frozenset):
                raise ContractError(f"{field} debe ser frozenset")
            for value in values:
                _required(value, field)
        if not self.unresolved_admission_ids.issubset(self.affected_admission_ids):
            raise ContractError("unresolved_admission_ids debe ser subconjunto de affected_admission_ids")
        if not isinstance(self.status, ForgetClosureStatus):
            raise ContractError("status debe ser ForgetClosureStatus")
        if (
            self.status is ForgetClosureStatus.SUPPRESSED
            and self.unresolved_admission_ids
        ):
            raise ContractError("SUPPRESSED requiere reconciliar todas las admisiones previas")



@dataclass(frozen=True, slots=True)
class ForgetRecoverySnapshot:
    """Estado mínimo que debe restaurarse antes de reabrir cualquier ruta.

    El snapshot es un contrato de datos para recuperación; no afirma que exista
    persistencia durable ni autentica por sí mismo el origen del registro.
    """

    generation: int
    closure: ForgetClosure
    admissions: tuple[ReadAdmission, ...]

    def __post_init__(self) -> None:
        _positive_int(self.generation, "generation")
        if not isinstance(self.closure, ForgetClosure):
            raise ContractError("closure debe ser ForgetClosure")
        if self.generation < self.closure.generation:
            raise ContractError("recovery no puede retroceder la generación")
        if not isinstance(self.admissions, tuple):
            raise ContractError("admissions debe ser tuple")
        if any(not isinstance(item, ReadAdmission) for item in self.admissions):
            raise ContractError("admissions solo puede contener ReadAdmission")
        admission_ids = tuple(item.admission_id for item in self.admissions)
        if len(admission_ids) != len(set(admission_ids)):
            raise ContractError("recovery no admite IDs de admisión duplicados")
        if frozenset(admission_ids) != self.closure.affected_admission_ids:
            raise ContractError("recovery requiere el inventario completo de admisiones afectadas")
        if any(
            item.target.memory_id != self.closure.target.memory_id
            or not item.route_ids.issubset(self.closure.delivery_route_ids)
            for item in self.admissions
        ):
            raise ContractError("admission fuera del objetivo o rutas del cierre")
        nonterminal = frozenset(
            item.admission_id
            for item in self.admissions
            if item.status not in (
                ReadAdmissionStatus.COMPLETED,
                ReadAdmissionStatus.CANCELLED,
            )
        )
        if nonterminal != self.closure.unresolved_admission_ids:
            raise ContractError("recovery y closure discrepan sobre admisiones no resueltas")
        if self.closure.status is ForgetClosureStatus.SUPPRESSED and nonterminal:
            raise ContractError("un cierre SUPPRESSED no puede recuperar admisiones abiertas")
