"""Catálogo cerrado de capacidades conocidas por Atlas."""

from dataclasses import dataclass
from enum import Enum

from atlas.assistant.planning import AssistantIntent, IntentKind
from atlas.core.errors import ContractError


class CapabilityRisk(str, Enum):
    """Clasificación mínima de impacto de una capacidad."""

    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Descripción declarativa; no contiene ni ejecuta un handler."""

    kind: IntentKind
    description: str
    parameter_names: tuple[str, ...]
    risk: CapabilityRisk
    result_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, IntentKind):
            raise ContractError("kind debe ser IntentKind")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ContractError("description debe ser texto no vacío")
        if not isinstance(self.parameter_names, tuple) or any(
            not isinstance(name, str) or not name.strip()
            for name in self.parameter_names
        ):
            raise ContractError("parameter_names debe ser una tupla de nombres")
        if len(self.parameter_names) != len(set(self.parameter_names)):
            raise ContractError("parameter_names no puede contener duplicados")
        if not isinstance(self.risk, CapabilityRisk):
            raise ContractError("risk debe ser CapabilityRisk")
        if not isinstance(self.result_type, str) or not self.result_type.strip():
            raise ContractError("result_type debe ser texto no vacío")


class CapabilityCatalog:
    """Registro inmutable y cerrado; listar una capacidad no la autoriza."""

    def __init__(self, definitions: tuple[CapabilityDefinition, ...]) -> None:
        if not isinstance(definitions, tuple) or any(
            not isinstance(item, CapabilityDefinition) for item in definitions
        ):
            raise ContractError("definitions debe ser una tupla de CapabilityDefinition")
        kinds = [item.kind for item in definitions]
        if len(kinds) != len(set(kinds)):
            raise ContractError("el catálogo no admite capacidades duplicadas")
        self._definitions = definitions
        self._by_kind = {item.kind: item for item in definitions}

    def list_all(self) -> tuple[CapabilityDefinition, ...]:
        """Devuelve el snapshot inmutable del catálogo."""
        return self._definitions

    def get(self, kind: IntentKind) -> CapabilityDefinition | None:
        """Busca una definición sin conceder autoridad ni resolver un handler."""
        if not isinstance(kind, IntentKind):
            raise ContractError("kind debe ser IntentKind")
        return self._by_kind.get(kind)

    def validate_intent(self, intent: AssistantIntent) -> CapabilityDefinition:
        """Comprueba que una intención usa una capacidad y parámetros catalogados."""
        if not isinstance(intent, AssistantIntent):
            raise ContractError("intent debe ser AssistantIntent")
        definition = self.get(intent.kind)
        if definition is None:
            raise ContractError("la capacidad no está registrada en el catálogo")
        supplied = {name for name, _ in intent.parameters}
        if supplied != set(definition.parameter_names):
            raise ContractError("los parámetros no coinciden con el contrato de capacidad")
        return definition


def build_default_capability_catalog() -> CapabilityCatalog:
    """Catálogo inicial explícito: solo listado y lectura de archivos."""
    return CapabilityCatalog((
        CapabilityDefinition(
            kind=IntentKind.WORKSPACE_LIST,
            description="Listar entradas inmediatas de un workspace configurado",
            parameter_names=("workspace_id",),
            risk=CapabilityRisk.READ_ONLY,
            result_type="WorkspaceListing",
        ),
        CapabilityDefinition(
            kind=IntentKind.WORKSPACE_READ,
            description="Leer un archivo UTF-8 mediante una ruta relativa del workspace",
            parameter_names=("workspace_id", "path"),
            risk=CapabilityRisk.READ_ONLY,
            result_type="WorkspaceFile",
        ),
    ))
