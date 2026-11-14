"""Adaptador de reloj del sistema que entrega instantes UTC."""

from datetime import datetime, timezone


class SystemClock:
    """Implementación estándar del puerto Clock."""

    def now(self) -> datetime:
        """Devuelve la hora actual con zona UTC explícita."""
        return datetime.now(timezone.utc)
