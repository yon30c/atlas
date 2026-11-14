"""Pure semantic reducer for the ME-03 consistency journal.

The reducer validates replay relationships. It does not authenticate journal
origin, prove anti-rollback, contact endpoints, or authorize protected reads.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from atlas.core.errors import ContractError
from atlas.memory.consistency import (
    AuthorityKind,
    AuthorizationRevisionSet,
    ReadAdmissionStatus,
    ReadTarget,
)
from atlas.memory.journal import (
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
)
from atlas.memory.models import MemoryScope, MemoryScopeKind


class EndpointProjectionStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    FENCED = "fenced"


@dataclass(frozen=True, slots=True)
class EndpointProjection:
    endpoint_id: str
    last_emission_sequence: int
    status: EndpointProjectionStatus
    receipt_ids: frozenset[str]
    terminal_receipt_id: str | None = None
    terminal_operation_id: str | None = None
    terminal_generation: int | None = None
    final_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class AdmissionProjection:
    admission_id: str
    operation_id: str
    memory_id: str
    version_id: str
    snapshot_id: str
    owner_id: str | None
    scope_kind: MemoryScopeKind | None
    scope_project_id: str | None
    admitted_at: datetime
    recoverable: bool
    generation: int
    revisions: AuthorizationRevisionSet
    route_ids: frozenset[str]
    status: ReadAdmissionStatus
    terminal_receipt_id: str | None
    terminal_operation_id: str | None
    terminal_generation: int | None
    endpoints: tuple[EndpointProjection, ...]


@dataclass(frozen=True, slots=True)
class ForgetProjection:
    operation_id: str
    memory_id: str
    generation: int
    affected_admission_ids: frozenset[str]
    route_ids: frozenset[str]
    suppressed: bool


@dataclass(frozen=True, slots=True)
class InvalidationProjection:
    operation_id: str
    authority_kind: AuthorityKind
    authority_id: str
    generation: int
    previous_revision: int
    new_revision: int
    affected_admission_ids: frozenset[str]
    route_ids: frozenset[str]
    reconciled: bool


@dataclass(frozen=True, slots=True)
class IdempotencyProjection:
    idempotency_key: str
    operation_id: str
    record_id: str


@dataclass(frozen=True, slots=True)
class RecoveryProjection:
    operation_id: str
    generation: int
    affected_admission_ids: frozenset[str]
    route_ids: frozenset[str]
    reconciled: bool
    terminal_receipt_id: str | None


@dataclass(frozen=True, slots=True)
class ConsistencyProjection:
    domain_id: str
    authority_epoch: int
    head_sequence: int
    admissions: tuple[AdmissionProjection, ...]
    forget_closures: tuple[ForgetProjection, ...]
    invalidations: tuple[InvalidationProjection, ...]
    idempotency_records: tuple[IdempotencyProjection, ...]
    receipt_ids: frozenset[str]
    recovery_closures: tuple[RecoveryProjection, ...] = ()
    emission_ids: frozenset[str] = frozenset()
    replay_metadata_version: int = 0


def reconstruct_read_target(admission: AdmissionProjection) -> ReadTarget | None:
    """Reconstruct only the exact v2 target; never infer a legacy scope."""
    if not isinstance(admission, AdmissionProjection) or not admission.recoverable:
        return None
    if not isinstance(admission.owner_id, str) or not admission.owner_id.strip():
        return None
    try:
        if admission.scope_kind is MemoryScopeKind.PRIVATE:
            if admission.scope_project_id is not None:
                return None
            scope = MemoryScope(MemoryScopeKind.PRIVATE)
        elif admission.scope_kind is MemoryScopeKind.PROJECT:
            if (
                not isinstance(admission.scope_project_id, str)
                or not admission.scope_project_id.strip()
            ):
                return None
            scope = MemoryScope(
                MemoryScopeKind.PROJECT,
                admission.scope_project_id,
            )
            project_revision = admission.revisions.project_revision
            if (
                project_revision is None
                or project_revision.authority_id != admission.scope_project_id
            ):
                return None
        else:
            return None
        return ReadTarget(
            memory_id=admission.memory_id,
            version_id=admission.version_id,
            owner_id=admission.owner_id,
            scope=scope,
        )
    except (ContractError, AttributeError, TypeError):
        return None


class ConsistencyJournalReducer:
    """Replays a structurally valid journal into an immutable metadata projection."""

    @staticmethod
    def _revision_for(
        revisions: AuthorizationRevisionSet, kind: AuthorityKind
    ):
        fields = {
            AuthorityKind.MEMORY: revisions.memory_revision,
            AuthorityKind.MEMORY_VERSION: revisions.version_revision,
            AuthorityKind.IDENTITY: revisions.identity_revision,
            AuthorityKind.PROJECT: revisions.project_revision,
            AuthorityKind.ENVIRONMENT: revisions.environment_revision,
            AuthorityKind.GRANT: revisions.grant_revision,
        }
        return fields.get(kind)

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise ContractError(message)

    def reduce(self, recovery: ConsistencyRecoveryState) -> ConsistencyProjection:
        """Replay a complete journal only when no checkpoint truncates its history."""
        return self._reduce(recovery, base_projection=None)

    def reduce_from_projection(
        self,
        recovery: ConsistencyRecoveryState,
        base_projection: ConsistencyProjection,
    ) -> ConsistencyProjection:
        """Continue replay from a complete, independently verified checkpoint projection.

        This method validates structural binding and replay metadata, but does not
        authenticate checkpoint storage or prove the caller obtained the projection
        from a trusted port. Only the recovery verifier may call it operationally.
        """
        return self._reduce(recovery, base_projection=base_projection)

    def _reduce(
        self,
        recovery: ConsistencyRecoveryState,
        base_projection: ConsistencyProjection | None,
    ) -> ConsistencyProjection:
        if not isinstance(recovery, ConsistencyRecoveryState):
            raise ContractError("recovery debe ser ConsistencyRecoveryState")
        if recovery.checkpoint is None:
            if base_projection is not None:
                raise ContractError("proyección base no aplica sin checkpoint")
        else:
            if not isinstance(base_projection, ConsistencyProjection):
                raise ContractError(
                    "checkpoint sin proyección base validada: recuperación fail-closed"
                )
            checkpoint = recovery.checkpoint
            if (
                base_projection.domain_id != recovery.domain_id
                or base_projection.authority_epoch != recovery.authority_epoch
                or base_projection.head_sequence != checkpoint.position.sequence
                or checkpoint.position.consistency_domain_id != recovery.domain_id
                or checkpoint.position.authority_epoch != recovery.authority_epoch
            ):
                raise ContractError("proyección base no coincide exactamente con checkpoint")
            if base_projection.replay_metadata_version != 1:
                raise ContractError("versión de metadatos de replay no soportada")
            if not isinstance(base_projection.emission_ids, frozenset):
                raise ContractError("emission_ids de proyección base no es frozenset")

        admissions = {}
        forgets = {}
        invalidations = {}
        invalidated_admissions = set()
        forgotten_memories = set()
        receipts = set()
        emission_ids = set()
        idempotency_records = {}
        latest_invalidation = {}
        recoveries = {}
        active_recovery = None
        latest_recovery_generation = 0

        if base_projection is not None:
            for item in base_projection.admissions:
                endpoints = {
                    endpoint.endpoint_id: {
                        "last_sequence": endpoint.last_emission_sequence,
                        "status": endpoint.status,
                        "receipt_ids": set(endpoint.receipt_ids),
                        "terminal_receipt_id": endpoint.terminal_receipt_id,
                        "terminal_operation_id": endpoint.terminal_operation_id,
                        "terminal_generation": endpoint.terminal_generation,
                        "final_sequence": endpoint.final_sequence,
                    }
                    for endpoint in item.endpoints
                }
                admissions[item.admission_id] = {
                    "operation_id": item.operation_id,
                    "memory_id": item.memory_id,
                    "version_id": item.version_id,
                    "snapshot_id": item.snapshot_id,
                    "owner_id": item.owner_id,
                    "scope_kind": item.scope_kind,
                    "scope_project_id": item.scope_project_id,
                    "admitted_at": item.admitted_at,
                    "recoverable": item.recoverable,
                    "generation": item.generation,
                    "revisions": item.revisions,
                    "route_ids": item.route_ids,
                    "status": item.status,
                    "terminal_receipt_id": item.terminal_receipt_id,
                    "terminal_operation_id": item.terminal_operation_id,
                    "terminal_generation": item.terminal_generation,
                    "endpoints": endpoints,
                }
            for item in base_projection.forget_closures:
                forgets[item.operation_id] = {
                    "memory_id": item.memory_id,
                    "generation": item.generation,
                    "affected_admission_ids": item.affected_admission_ids,
                    "route_ids": item.route_ids,
                    "suppressed": item.suppressed,
                }
                forgotten_memories.add(item.memory_id)
            for item in base_projection.invalidations:
                invalidations[item.operation_id] = {
                    "authority_kind": item.authority_kind,
                    "authority_id": item.authority_id,
                    "generation": item.generation,
                    "previous_revision": item.previous_revision,
                    "new_revision": item.new_revision,
                    "affected_admission_ids": item.affected_admission_ids,
                    "route_ids": item.route_ids,
                    "reconciled": item.reconciled,
                }
                invalidated_admissions.update(item.affected_admission_ids)
                key = (item.authority_kind, item.authority_id)
                previous = latest_invalidation.get(key)
                if previous is None or item.new_revision > previous["new_revision"]:
                    latest_invalidation[key] = invalidations[item.operation_id]
            for item in base_projection.recovery_closures:
                recoveries[item.operation_id] = {
                    "generation": item.generation,
                    "affected_admission_ids": item.affected_admission_ids,
                    "route_ids": item.route_ids,
                    "reconciled": item.reconciled,
                    "terminal_receipt_id": item.terminal_receipt_id,
                }
                if item.reconciled:
                    latest_recovery_generation = max(
                        latest_recovery_generation, item.generation
                    )
                elif active_recovery is None:
                    active_recovery = item.operation_id
                else:
                    raise ContractError("proyección base contiene múltiples recovery activos")
            receipts.update(base_projection.receipt_ids)
            emission_ids.update(base_projection.emission_ids)
            idempotency_records.update({
                item.idempotency_key: (item.operation_id, item.record_id)
                for item in base_projection.idempotency_records
            })

        def admission_for(transition: ConsistencyTransition):
            item = admissions.get(transition.admission_id)
            self._require(item is not None, "transición referencia una admisión inexistente")
            self._require(
                item["generation"] == transition.generation,
                "generación de transición no coincide con la admisión",
            )
            self._require(
                transition.operation_id == item["operation_id"],
                "operation_id no coincide con la admisión",
            )
            return item

        def add_receipt(receipt_id: str) -> None:
            self._require(receipt_id not in receipts, "receipt_id duplicado en journal")
            receipts.add(receipt_id)

        for entry in recovery.entries:
            transition = entry.transition
            kind = transition.record_kind
            if transition.idempotency_key is not None:
                self._require(
                    transition.idempotency_key not in idempotency_records,
                    "idempotency_key duplicada en journal",
                )
                idempotency_records[transition.idempotency_key] = (
                    transition.operation_id, transition.record_id
                )

            if kind is ConsistencyRecordKind.READ_ADMITTED:
                self._require(
                    active_recovery is None,
                    "READ_ADMITTED durante recuperación pendiente del dominio",
                )
                self._require(
                    transition.generation >= latest_recovery_generation,
                    "READ_ADMITTED usa generación anterior a la última recuperación",
                )
                admission_id = transition.admission_id
                self._require(
                    admission_id not in admissions,
                    "READ_ADMITTED duplica admission_id",
                )
                self._require(
                    transition.memory_id not in forgotten_memories,
                    "READ_ADMITTED posterior a FORGET_CLOSED",
                )
                self._require(
                    transition.operation_id == f"read:{admission_id}",
                    "READ_ADMITTED operation_id no corresponde a su admisión",
                )
                for (authority_kind, authority_id), latest in latest_invalidation.items():
                    revision = self._revision_for(transition.revisions, authority_kind)
                    if revision is not None and revision.authority_id == authority_id:
                        self._require(
                            latest["reconciled"],
                            "READ_ADMITTED antes de reconciliar la invalidación aplicable",
                        )
                        self._require(
                            revision.revision >= latest["new_revision"]
                            and transition.generation >= latest["generation"],
                            "READ_ADMITTED utiliza revisión o generación invalidada",
                        )
                endpoints = {
                    endpoint_id: {
                        "last_sequence": 0,
                        "status": EndpointProjectionStatus.OPEN,
                        "receipt_ids": set(),
                        "terminal_receipt_id": None,
                        "terminal_operation_id": None,
                        "terminal_generation": None,
                        "final_sequence": None,
                    }
                    for endpoint_id in transition.route_ids
                }
                admissions[admission_id] = {
                    "operation_id": transition.operation_id,
                    "memory_id": transition.memory_id,
                    "version_id": transition.version_id,
                    "snapshot_id": transition.snapshot_id,
                    "owner_id": transition.owner_id,
                    "scope_kind": transition.scope_kind,
                    "scope_project_id": transition.scope_project_id,
                    "admitted_at": transition.occurred_at,
                    "recoverable": transition.schema_version == 2,
                    "generation": transition.generation,
                    "revisions": transition.revisions,
                    "route_ids": transition.route_ids,
                    "status": ReadAdmissionStatus.ADMITTED,
                    "terminal_receipt_id": None,
                    "terminal_operation_id": None,
                    "terminal_generation": None,
                    "endpoints": endpoints,
                }
                continue

            if kind is ConsistencyRecordKind.READ_ACTIVATED:
                self._require(
                    active_recovery is None,
                    "READ_ACTIVATED durante recuperación pendiente",
                )
                item = admission_for(transition)
                self._require(
                    item["status"] is ReadAdmissionStatus.ADMITTED,
                    "READ_ACTIVATED requiere admisión ADMITTED",
                )
                item["status"] = ReadAdmissionStatus.ACTIVE
                continue

            if kind is ConsistencyRecordKind.EGRESS_COMMITTED:
                self._require(
                    active_recovery is None,
                    "egress prohibido mientras el dominio se recupera",
                )
                item = admission_for(transition)
                endpoint = item["endpoints"].get(transition.endpoint_id)
                self._require(endpoint is not None, "egress usa endpoint no admitido")
                self._require(
                    endpoint["status"] is EndpointProjectionStatus.OPEN,
                    "egress posterior a finalización o fencing",
                )
                self._require(
                    transition.admission_id not in invalidated_admissions,
                    "egress posterior a invalidación",
                )
                self._require(
                    transition.admission_id not in {
                        admission_id
                        for closure in forgets.values()
                        for admission_id in closure["affected_admission_ids"]
                    },
                    "egress posterior a FORGET_CLOSED",
                )
                self._require(
                    transition.emission_sequence > endpoint["last_sequence"],
                    "secuencia de emisión duplicada o regresiva",
                )
                self._require(
                    transition.emission_id not in emission_ids,
                    "emission_id duplicado en journal",
                )
                add_receipt(transition.receipt_id)
                emission_ids.add(transition.emission_id)
                endpoint["last_sequence"] = transition.emission_sequence
                endpoint["receipt_ids"].add(transition.receipt_id)
                item["status"] = ReadAdmissionStatus.ACTIVE
                continue

            if kind in (
                ConsistencyRecordKind.ENDPOINT_COMPLETED,
                ConsistencyRecordKind.ENDPOINT_FENCED,
            ):
                item = admissions.get(transition.admission_id)
                self._require(item is not None, "recibo referencia una admisión inexistente")
                endpoint = item["endpoints"].get(transition.endpoint_id)
                self._require(endpoint is not None, "recibo usa endpoint no admitido")
                self._require(
                    endpoint["status"] is EndpointProjectionStatus.OPEN,
                    "endpoint ya tiene estado terminal",
                )
                if kind is ConsistencyRecordKind.ENDPOINT_COMPLETED:
                    self._require(
                        active_recovery is None,
                        "finalización ordinaria prohibida durante recovery fencing",
                    )
                    if transition.operation_id == item["operation_id"]:
                        expected_generation = item["generation"]
                        self._require(
                            transition.admission_id not in invalidated_admissions
                            and not any(
                                transition.admission_id in closure["affected_admission_ids"]
                                for closure in forgets.values()
                            ),
                            "finalización de lectura usa operación anterior al cierre",
                        )
                    else:
                        closure = forgets.get(transition.operation_id)
                        invalidation = invalidations.get(transition.operation_id)
                        operation = closure if closure is not None else invalidation
                        self._require(
                            operation is not None
                            and transition.admission_id in operation["affected_admission_ids"],
                            "finalización no corresponde a la lectura o cierre exacto",
                        )
                        expected_generation = operation["generation"]
                    self._require(
                        transition.generation == expected_generation,
                        "generación del recibo de finalización no coincide con la operación",
                    )
                    self._require(
                        transition.final_sequence >= endpoint["last_sequence"],
                        "final_sequence precede una emisión comprometida",
                    )
                    endpoint["status"] = EndpointProjectionStatus.COMPLETED
                else:
                    closure = forgets.get(transition.operation_id)
                    invalidation = invalidations.get(transition.operation_id)
                    recovery_closure = recoveries.get(transition.operation_id)
                    operation = (
                        closure if closure is not None
                        else invalidation if invalidation is not None
                        else recovery_closure
                    )
                    self._require(
                        operation is not None
                        and transition.admission_id in operation["affected_admission_ids"],
                        "ENDPOINT_FENCED requiere el cierre exacto que afecta la admisión",
                    )
                    self._require(
                        transition.generation == operation["generation"]
                        and transition.generation > item["generation"],
                        "ENDPOINT_FENCED debe usar la nueva generación del cierre",
                    )
                    if recovery_closure is not None:
                        self._require(
                            active_recovery == transition.operation_id
                            and item["status"] is ReadAdmissionStatus.UNRESOLVED,
                            "fencing de recovery requiere admisión UNRESOLVED",
                        )
                    endpoint["status"] = EndpointProjectionStatus.FENCED
                add_receipt(transition.receipt_id)
                endpoint["receipt_ids"].add(transition.receipt_id)
                endpoint["terminal_receipt_id"] = transition.receipt_id
                endpoint["terminal_operation_id"] = transition.operation_id
                endpoint["terminal_generation"] = transition.generation
                endpoint["final_sequence"] = (
                    transition.final_sequence
                    if kind is ConsistencyRecordKind.ENDPOINT_COMPLETED
                    else None
                )
                continue

            if kind is ConsistencyRecordKind.ADMISSION_RECONCILED:
                item = admissions.get(transition.admission_id)
                self._require(item is not None, "reconciliación referencia una admisión inexistente")
                recovery_closure = recoveries.get(transition.operation_id)
                self._require(
                    transition.operation_id == item["operation_id"]
                    or (
                        transition.operation_id in forgets
                        and transition.admission_id in forgets[transition.operation_id]["affected_admission_ids"]
                    )
                    or (
                        transition.operation_id in invalidations
                        and transition.admission_id in invalidations[transition.operation_id]["affected_admission_ids"]
                    )
                    or (
                        recovery_closure is not None
                        and transition.admission_id in recovery_closure["affected_admission_ids"]
                    ),
                    "reconciliación no corresponde a la operación exacta",
                )
                expected_generation = (
                    recovery_closure["generation"]
                    if recovery_closure is not None
                    else item["generation"]
                )
                self._require(
                    transition.generation == expected_generation,
                    "ADMISSION_RECONCILED debe identificar la generación de la operación",
                )
                self._require(
                    item["status"] not in (
                        ReadAdmissionStatus.COMPLETED,
                        ReadAdmissionStatus.CANCELLED,
                    ),
                    "admisión ya reconciliada",
                )
                endpoint_states = tuple(
                    endpoint["status"] for endpoint in item["endpoints"].values()
                )
                self._require(
                    all(state is not EndpointProjectionStatus.OPEN for state in endpoint_states),
                    "ADMISSION_RECONCILED con endpoints no terminales",
                )
                terminal = transition.admission_terminal_status
                if terminal is ReadAdmissionStatus.COMPLETED:
                    self._require(
                        all(state is EndpointProjectionStatus.COMPLETED for state in endpoint_states),
                        "COMPLETED requiere todos los endpoints completados",
                    )
                else:
                    self._require(
                        any(state is EndpointProjectionStatus.FENCED for state in endpoint_states),
                        "CANCELLED requiere al menos un endpoint cercado",
                    )
                add_receipt(transition.receipt_id)
                item["status"] = terminal
                item["terminal_receipt_id"] = transition.receipt_id
                item["terminal_operation_id"] = transition.operation_id
                item["terminal_generation"] = transition.generation
                continue

            if kind is ConsistencyRecordKind.FORGET_CLOSED:
                self._require(
                    active_recovery is None,
                    "FORGET_CLOSED durante recuperación pendiente",
                )
                memory_id = transition.memory_id
                self._require(memory_id not in forgotten_memories, "memoria ya tiene FORGET_CLOSED")
                related = {
                    admission_id: item
                    for admission_id, item in admissions.items()
                    if item["memory_id"] == memory_id
                    and item["status"] not in (
                        ReadAdmissionStatus.COMPLETED,
                        ReadAdmissionStatus.CANCELLED,
                    )
                }
                expected_ids = frozenset(related)
                self._require(
                    not any(
                        not invalidation["reconciled"]
                        and (
                            invalidation["authority_kind"] is AuthorityKind.MEMORY
                            and invalidation["authority_id"] == memory_id
                            or bool(expected_ids.intersection(invalidation["affected_admission_ids"]))
                        )
                        for invalidation in invalidations.values()
                    ),
                    "FORGET_CLOSED se solapa con una invalidación pendiente",
                )
                expected_routes = frozenset(
                    route for item in related.values() for route in item["route_ids"]
                )
                self._require(
                    transition.affected_admission_ids == expected_ids,
                    "FORGET_CLOSED no captura todas las admisiones previas no terminales",
                )
                self._require(
                    transition.route_ids == expected_routes,
                    "FORGET_CLOSED no captura todas las rutas previas",
                )
                prior_generations = [
                    item["generation"] for item in admissions.values()
                    if item["memory_id"] == memory_id
                ]
                self._require(
                    not prior_generations or transition.generation > max(prior_generations),
                    "FORGET_CLOSED no avanza la generación",
                )
                self._require(
                    transition.operation_id not in forgets,
                    "operation_id de Forget duplicado",
                )
                forgotten_memories.add(memory_id)
                forgets[transition.operation_id] = {
                    "memory_id": memory_id,
                    "generation": transition.generation,
                    "affected_admission_ids": expected_ids,
                    "route_ids": expected_routes,
                    "suppressed": False,
                }
                continue

            if kind is ConsistencyRecordKind.FORGET_SUPPRESSED:
                closure = forgets.get(transition.operation_id)
                self._require(closure is not None, "FORGET_SUPPRESSED sin cierre previo")
                self._require(
                    transition.memory_id == closure["memory_id"]
                    and transition.generation == closure["generation"]
                    and transition.affected_admission_ids == closure["affected_admission_ids"]
                    and transition.route_ids == closure["route_ids"],
                    "FORGET_SUPPRESSED no coincide con el cierre",
                )
                self._require(not closure["suppressed"], "FORGET_SUPPRESSED duplicado")
                self._require(
                    all(
                        admissions[admission_id]["status"] in (
                            ReadAdmissionStatus.COMPLETED,
                            ReadAdmissionStatus.CANCELLED,
                        )
                        for admission_id in closure["affected_admission_ids"]
                    ),
                    "FORGET_SUPPRESSED con admisiones no terminales",
                )
                closure["suppressed"] = True
                continue

            if kind is ConsistencyRecordKind.INVALIDATION_CLOSED:
                self._require(
                    active_recovery is None,
                    "INVALIDATION_CLOSED durante recuperación pendiente",
                )
                self._require(
                    transition.operation_id not in invalidations,
                    "operation_id de invalidación duplicado",
                )
                key = (transition.authority_kind, transition.authority_id)
                self._require(
                    not (
                        transition.authority_kind is AuthorityKind.MEMORY
                        and transition.authority_id in forgotten_memories
                    ),
                    "INVALIDATION_CLOSED no puede reabrir una memoria con Forget cerrado",
                )
                previous = latest_invalidation.get(key)
                self._require(
                    previous is None or previous["reconciled"],
                    "invalidación anterior del mismo recurso sigue pendiente",
                )
                if previous is not None:
                    self._require(
                        transition.previous_revision == previous["new_revision"],
                        "INVALIDATION_CLOSED rompe continuidad de revisiones",
                    )
                related = {}
                for admission_id, item in admissions.items():
                    if item["status"] in (
                        ReadAdmissionStatus.COMPLETED,
                        ReadAdmissionStatus.CANCELLED,
                    ):
                        continue
                    revision = self._revision_for(item["revisions"], transition.authority_kind)
                    if (
                        revision is not None
                        and revision.authority_id == transition.authority_id
                        and revision.revision == transition.previous_revision
                    ):
                        related[admission_id] = item
                expected_ids = frozenset(related)
                self._require(
                    not any(
                        bool(expected_ids.intersection(closure["affected_admission_ids"]))
                        for closure in forgets.values()
                    )
                    and not any(
                        not other["reconciled"]
                        and bool(expected_ids.intersection(other["affected_admission_ids"]))
                        for other in invalidations.values()
                    ),
                    "INVALIDATION_CLOSED se solapa con otro cierre pendiente",
                )
                expected_routes = frozenset(
                    route for item in related.values() for route in item["route_ids"]
                )
                self._require(
                    transition.affected_admission_ids == expected_ids,
                    "INVALIDATION_CLOSED no captura todas las admisiones afectadas",
                )
                self._require(
                    transition.route_ids == expected_routes,
                    "INVALIDATION_CLOSED no captura todas las rutas afectadas",
                )
                self._require(
                    not related or transition.generation > max(
                        item["generation"] for item in related.values()
                    ),
                    "INVALIDATION_CLOSED no avanza la generación afectada",
                )
                invalidated_admissions.update(expected_ids)
                invalidations[transition.operation_id] = {
                    "authority_kind": transition.authority_kind,
                    "authority_id": transition.authority_id,
                    "generation": transition.generation,
                    "previous_revision": transition.previous_revision,
                    "new_revision": transition.new_revision,
                    "affected_admission_ids": expected_ids,
                    "route_ids": expected_routes,
                    "reconciled": False,
                }
                latest_invalidation[key] = invalidations[transition.operation_id]
                continue

            if kind is ConsistencyRecordKind.INVALIDATION_RECONCILED:
                closure = invalidations.get(transition.operation_id)
                self._require(closure is not None, "INVALIDATION_RECONCILED sin cierre previo")
                self._require(
                    transition.authority_kind is closure["authority_kind"]
                    and transition.authority_id == closure["authority_id"]
                    and transition.generation == closure["generation"]
                    and transition.affected_admission_ids == closure["affected_admission_ids"]
                    and transition.route_ids == closure["route_ids"],
                    "INVALIDATION_RECONCILED no coincide con su cierre",
                )
                self._require(not closure["reconciled"], "INVALIDATION_RECONCILED duplicado")
                self._require(
                    all(
                        admissions[admission_id]["status"] in (
                            ReadAdmissionStatus.COMPLETED,
                            ReadAdmissionStatus.CANCELLED,
                        )
                        for admission_id in closure["affected_admission_ids"]
                    ),
                    "INVALIDATION_RECONCILED con admisiones no terminales",
                )
                closure["reconciled"] = True
                continue

            if kind is ConsistencyRecordKind.RECOVERY_CLOSED:
                self._require(
                    active_recovery is None,
                    "ya existe una recuperación del dominio pendiente",
                )
                self._require(
                    all(item["reconciled"] for item in invalidations.values()),
                    "RECOVERY_CLOSED no puede adelantarse a una invalidación pendiente",
                )
                self._require(
                    all(
                        admissions[admission_id]["status"] in (
                            ReadAdmissionStatus.COMPLETED,
                            ReadAdmissionStatus.CANCELLED,
                        )
                        for closure in forgets.values()
                        for admission_id in closure["affected_admission_ids"]
                    ),
                    "RECOVERY_CLOSED no puede adelantarse a un Forget pendiente",
                )
                expected_ids = frozenset(
                    admission_id
                    for admission_id, item in admissions.items()
                    if item["status"] not in (
                        ReadAdmissionStatus.COMPLETED,
                        ReadAdmissionStatus.CANCELLED,
                    )
                )
                expected_routes = frozenset(
                    route
                    for admission_id in expected_ids
                    for route in admissions[admission_id]["route_ids"]
                )
                self._require(bool(expected_ids), "RECOVERY_CLOSED sin admisiones pendientes")
                self._require(
                    transition.affected_admission_ids == expected_ids
                    and transition.route_ids == expected_routes,
                    "RECOVERY_CLOSED debe incluir todas las admisiones y rutas pendientes",
                )
                prior_generations = [
                    item["generation"] for item in admissions.values()
                ] + [
                    item["generation"] for item in forgets.values()
                ] + [
                    item["generation"] for item in invalidations.values()
                ]
                self._require(
                    not prior_generations
                    or transition.generation > max(prior_generations),
                    "RECOVERY_CLOSED debe avanzar todas las generaciones previas",
                )
                expected_operation = (
                    f"recovery:{recovery.domain_id}:"
                    f"{recovery.authority_epoch}:{transition.generation}"
                )
                self._require(
                    transition.operation_id == expected_operation
                    and transition.operation_id not in recoveries,
                    "operation_id de recuperación no es único o canónico",
                )
                for admission_id in expected_ids:
                    admissions[admission_id]["status"] = ReadAdmissionStatus.UNRESOLVED
                recoveries[transition.operation_id] = {
                    "generation": transition.generation,
                    "affected_admission_ids": expected_ids,
                    "route_ids": expected_routes,
                    "reconciled": False,
                    "terminal_receipt_id": None,
                }
                active_recovery = transition.operation_id
                continue

            if kind is ConsistencyRecordKind.RECOVERY_RECONCILED:
                closure = recoveries.get(transition.operation_id)
                self._require(
                    closure is not None and active_recovery == transition.operation_id,
                    "RECOVERY_RECONCILED sin cierre activo",
                )
                self._require(
                    transition.generation == closure["generation"]
                    and transition.affected_admission_ids == closure["affected_admission_ids"]
                    and transition.route_ids == closure["route_ids"],
                    "RECOVERY_RECONCILED no coincide con el cierre",
                )
                self._require(
                    not closure["reconciled"]
                    and all(
                        admissions[admission_id]["status"] in (
                            ReadAdmissionStatus.COMPLETED,
                            ReadAdmissionStatus.CANCELLED,
                        )
                        for admission_id in closure["affected_admission_ids"]
                    ),
                    "RECOVERY_RECONCILED con admisiones pendientes o duplicado",
                )
                add_receipt(transition.receipt_id)
                closure["terminal_receipt_id"] = transition.receipt_id
                closure["reconciled"] = True
                active_recovery = None
                latest_recovery_generation = max(
                    latest_recovery_generation, closure["generation"]
                )
                continue

            if kind is ConsistencyRecordKind.CHECKPOINT_COMMITTED:
                continue

            raise ContractError("tipo de transición desconocido")

        admission_projection = tuple(
            AdmissionProjection(
                admission_id=admission_id,
                operation_id=item["operation_id"],
                memory_id=item["memory_id"],
                version_id=item["version_id"],
                snapshot_id=item["snapshot_id"],
                owner_id=item["owner_id"],
                scope_kind=item["scope_kind"],
                scope_project_id=item["scope_project_id"],
                admitted_at=item["admitted_at"],
                recoverable=item["recoverable"],
                generation=item["generation"],
                revisions=item["revisions"],
                route_ids=item["route_ids"],
                status=item["status"],
                terminal_receipt_id=item["terminal_receipt_id"],
                terminal_operation_id=item["terminal_operation_id"],
                terminal_generation=item["terminal_generation"],
                endpoints=tuple(
                    EndpointProjection(
                        endpoint_id=endpoint_id,
                        last_emission_sequence=endpoint["last_sequence"],
                        status=endpoint["status"],
                        receipt_ids=frozenset(endpoint["receipt_ids"]),
                        terminal_receipt_id=endpoint["terminal_receipt_id"],
                        terminal_operation_id=endpoint["terminal_operation_id"],
                        terminal_generation=endpoint["terminal_generation"],
                        final_sequence=endpoint["final_sequence"],
                    )
                    for endpoint_id, endpoint in sorted(item["endpoints"].items())
                ),
            )
            for admission_id, item in sorted(admissions.items())
        )
        forget_projection = tuple(
            ForgetProjection(
                operation_id=operation_id,
                memory_id=item["memory_id"],
                generation=item["generation"],
                affected_admission_ids=item["affected_admission_ids"],
                route_ids=item["route_ids"],
                suppressed=item["suppressed"],
            )
            for operation_id, item in sorted(forgets.items())
        )
        invalidation_projection = tuple(
            InvalidationProjection(
                operation_id=operation_id,
                authority_kind=item["authority_kind"],
                authority_id=item["authority_id"],
                generation=item["generation"],
                previous_revision=item["previous_revision"],
                new_revision=item["new_revision"],
                affected_admission_ids=item["affected_admission_ids"],
                route_ids=item["route_ids"],
                reconciled=item["reconciled"],
            )
            for operation_id, item in sorted(invalidations.items())
        )
        recovery_projection = tuple(
            RecoveryProjection(
                operation_id=operation_id,
                generation=item["generation"],
                affected_admission_ids=item["affected_admission_ids"],
                route_ids=item["route_ids"],
                reconciled=item["reconciled"],
                terminal_receipt_id=item["terminal_receipt_id"],
            )
            for operation_id, item in sorted(recoveries.items())
        )
        return ConsistencyProjection(
            domain_id=recovery.domain_id,
            authority_epoch=recovery.authority_epoch,
            head_sequence=recovery.head_sequence,
            admissions=admission_projection,
            forget_closures=forget_projection,
            invalidations=invalidation_projection,
            idempotency_records=tuple(
                IdempotencyProjection(key, value[0], value[1])
                for key, value in sorted(idempotency_records.items())
            ),
            receipt_ids=frozenset(receipts),
            recovery_closures=recovery_projection,
            emission_ids=frozenset(emission_ids),
            replay_metadata_version=1,
        )
