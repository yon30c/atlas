"""Puerto mínimo para eventos del dominio."""
from typing import Protocol, Sequence

from atlas.assistant.models import DomainEvent


class EventStore(Protocol):
    def append(self, event: DomainEvent) -> None:
        """Añade un evento inmutable."""

    def by_correlation(self, correlation_id: str) -> Sequence[DomainEvent]:
        """Recupera eventos de una correlación."""