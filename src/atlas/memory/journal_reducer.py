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
)
from atlas.memory.journal import (
    ConsistencyRecordKind,
    ConsistencyRecoveryState,
    ConsistencyTransition,
)
from atlas.memory.models import MemoryScopeKind


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
class ConsistencyProjection:
    domain_id: str
    authority_epoch: int
    head_sequence: int
    admissions: tuple[AdmissionProjection, ...]
    forget_closures: tuple[ForgetProjection, ...]
    invalidations: tuple[InvalidationProjection, ...]
    idempotency_records: tuple[IdempotencyProjection, ...]
    receipt_ids: frozenset[str]


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
        if not isinstance(recovery, ConsistencyRecoveryState):
            raise ContractError("recovery debe ser ConsistencyRecoveryState")
        if recovery.checkpoint is not None:
            raise ContractError(
                "checkpoint sin proyección base validada: recuperación fail-closed"
            )

        admissions = {}
        forgets = {}
        invalidations = {}
        invalidated_admissions = set()
        forgotten_memories = set()
        receipts = set()
        emission_ids = set()
        idempotency_records = {}
        latest_invalidation = {}

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
                    "endpoints": endpoints,
                }
                continue

            if kind is ConsistencyRecordKind.READ_ACTIVATED:
                item = admission_for(transition)
                self._require(
                    item["status"] is ReadAdmissionStatus.ADMITTED,
                    "READ_ACTIVATED requiere admisión ADMITTED",
                )
                item["status"] = ReadAdmissionStatus.ACTIVE
                continue

            if kind is ConsistencyRecordKind.EGRESS_COMMITTED:
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
                    operation = closure if closure is not None else invalidation
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
                    endpoint["status"] = EndpointProjectionStatus.FENCED
                add_receipt(transition.receipt_id)
                endpoint["receipt_ids"].add(transition.receipt_id)
                endpoint["terminal_receipt_id"] = transition.receipt_id
                continue

            if kind is ConsistencyRecordKind.ADMISSION_RECONCILED:
                item = admissions.get(transition.admission_id)
                self._require(item is not None, "reconciliación referencia una admisión inexistente")
                self._require(
                    transition.operation_id == item["operation_id"]
                    or (
                        transition.operation_id in forgets
                        and transition.admission_id in forgets[transition.operation_id]["affected_admission_ids"]
                    )
                    or (
                        transition.operation_id in invalidations
                        and transition.admission_id in invalidations[transition.operation_id]["affected_admission_ids"]
                    ),
                    "reconciliación no corresponde a la operación exacta",
                )
                self._require(
                    transition.generation == item["generation"],
                    "ADMISSION_RECONCILED debe identificar la generación de la admisión",
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
                continue

            if kind is ConsistencyRecordKind.FORGET_CLOSED:
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
                endpoints=tuple(
                    EndpointProjection(
                        endpoint_id=endpoint_id,
                        last_emission_sequence=endpoint["last_sequence"],
                        status=endpoint["status"],
                        receipt_ids=frozenset(endpoint["receipt_ids"]),
                        terminal_receipt_id=endpoint["terminal_receipt_id"],
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
        )
