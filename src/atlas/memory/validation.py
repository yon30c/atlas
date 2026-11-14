"""Validadores puros de agregados, propuestas y transiciones de memoria."""
from atlas.core.errors import ContractError
from atlas.memory.models import (
    Memory,
    MemoryProposal,
    MemoryVersion,
    MemoryVersionStatus,
    MemoryProposalIntent,
)


def validate_memory_aggregate(memory: Memory, versions: tuple[MemoryVersion, ...]) -> None:
    if not isinstance(memory, Memory):
        raise ContractError("memory debe ser Memory")
    if not isinstance(versions, tuple):
        raise ContractError("versions debe ser tuple")
    if any(not isinstance(version, MemoryVersion) for version in versions):
        raise ContractError("versions solo admite MemoryVersion")

    by_id: dict[str, MemoryVersion] = {}
    by_number: dict[int, MemoryVersion] = {}
    for version in versions:
        if version.memory_id != memory.memory_id:
            raise ContractError("todas las versiones deben pertenecer a la memoria")
        if version.version_id in by_id:
            raise ContractError("version_id duplicado")
        if version.version_number in by_number:
            raise ContractError("version_number duplicado")
        by_id[version.version_id] = version
        by_number[version.version_number] = version

    if versions and 1 not in by_number:
        raise ContractError("el historial debe comenzar en version_number 1")

    for number, version in by_number.items():
        if number == 1:
            if version.parent_version_id is not None:
                raise ContractError("la primera versión no puede tener padre")
            continue
        if version.parent_version_id is None:
            raise ContractError("las versiones posteriores requieren parent_version_id")
        parent = by_id.get(version.parent_version_id)
        if parent is None:
            raise ContractError("parent_version_id no existe en el mismo agregado")
        if parent.version_number >= version.version_number:
            raise ContractError("el padre debe tener un version_number menor")

    approved = tuple(v for v in versions if v.status is MemoryVersionStatus.APPROVED)
    if memory.current_approved_version_id is None:
        if approved:
            raise ContractError("no puede haber versión approved sin puntero vigente")
    else:
        if len(approved) != 1 or approved[0].version_id != memory.current_approved_version_id:
            raise ContractError("el puntero vigente debe identificar la única versión approved")


def validate_proposal_links(
    memory: Memory,
    version: MemoryVersion,
    proposal: MemoryProposal,
    existing_versions: tuple[MemoryVersion, ...] = (),
) -> None:
    if not isinstance(memory, Memory) or not isinstance(version, MemoryVersion) or not isinstance(proposal, MemoryProposal):
        raise ContractError("memory, version y proposal deben ser modelos de dominio")
    if proposal.memory_id != memory.memory_id or version.memory_id != memory.memory_id:
        raise ContractError("la propuesta y versión deben pertenecer a memory")
    if proposal.version_id != version.version_id:
        raise ContractError("proposal.version_id no coincide con version.version_id")
    if proposal.submitted_at != version.submitted_at:
        raise ContractError("proposal.submitted_at debe coincidir con version.submitted_at")
    if version.status is not MemoryVersionStatus.PENDING_REVIEW:
        raise ContractError("la versión propuesta debe estar pending_review")
    if not isinstance(existing_versions, tuple):
        raise ContractError("existing_versions debe ser tuple")

    validate_memory_aggregate(memory, existing_versions)
    if any(item.version_id == version.version_id for item in existing_versions):
        raise ContractError("la versión propuesta ya existe en el historial")

    if proposal.intent is MemoryProposalIntent.CREATE_MEMORY:
        if memory.current_approved_version_id is not None or existing_versions:
            raise ContractError("CREATE_MEMORY requiere una memoria sin historial ni versión vigente")
        if version.version_number != 1 or version.parent_version_id is not None:
            raise ContractError("CREATE_MEMORY requiere la primera versión sin padre")
    elif proposal.intent is MemoryProposalIntent.NEW_VERSION:
        if memory.current_approved_version_id is None:
            raise ContractError("NEW_VERSION requiere una versión approved vigente")
        current = next(
            (item for item in existing_versions if item.version_id == memory.current_approved_version_id),
            None,
        )
        if current is None:
            raise ContractError("el snapshot debe incluir la versión approved vigente")
        next_number = max(item.version_number for item in existing_versions) + 1
        if version.parent_version_id != current.version_id:
            raise ContractError("NEW_VERSION debe referir a la versión approved vigente")
        if version.version_number != next_number:
            raise ContractError("NEW_VERSION debe usar el siguiente número no reutilizado")
    else:
        raise ContractError("intent de propuesta desconocido")


def validate_version_transition(current: MemoryVersionStatus, target: MemoryVersionStatus) -> None:
    allowed = {
        (MemoryVersionStatus.PENDING_REVIEW, MemoryVersionStatus.APPROVED),
        (MemoryVersionStatus.PENDING_REVIEW, MemoryVersionStatus.REJECTED),
        (MemoryVersionStatus.APPROVED, MemoryVersionStatus.SUPERSEDED),
        (MemoryVersionStatus.APPROVED, MemoryVersionStatus.FORGOTTEN),
    }
    if not isinstance(current, MemoryVersionStatus) or not isinstance(target, MemoryVersionStatus):
        raise ContractError("current y target deben ser MemoryVersionStatus")
    if (current, target) not in allowed:
        raise ContractError("transición de MemoryVersion no permitida")
