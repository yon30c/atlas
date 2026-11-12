"""Puerto para obtener el instante actual."""
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Devuelve un instante consciente de zona horaria en UTC."""