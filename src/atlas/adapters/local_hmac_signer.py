"""Production HMAC signer using an explicitly configured active-key provider."""
from atlas.core.errors import ContractError
from atlas.memory.envelope import AuthenticatedConsistencyEnvelope
from atlas.memory.local_auth import authenticate_envelope
from atlas.memory.local_keys import ActiveLocalConsistencyKey
from atlas.ports.active_local_consistency_keys import ActiveLocalConsistencyKeyProvider
from atlas.ports.local_consistency_signer import LocalConsistencySignerPort


class HmacLocalConsistencySigner(LocalConsistencySignerPort):
    """Sign exact envelope/object pairs without exposing key custody to the journal."""

    def __init__(self, active_key_provider: ActiveLocalConsistencyKeyProvider) -> None:
        if active_key_provider is None or not callable(
            getattr(active_key_provider, "load_active_key", None)
        ):
            raise ContractError("active_key_provider debe implementar load_active_key")
        self._active_key_provider = active_key_provider

    def sign_envelope(self, envelope, object_value):
        if not isinstance(envelope, AuthenticatedConsistencyEnvelope):
            raise ContractError("envelope debe ser AuthenticatedConsistencyEnvelope")
        active_key = self._active_key_provider.load_active_key()
        if active_key is None:
            raise OSError("clave HMAC activa no disponible")
        if not isinstance(active_key, ActiveLocalConsistencyKey):
            raise ContractError("active key provider devolvió un tipo no válido")
        if active_key.key_reference != envelope.key_reference:
            raise ContractError("la clave activa no coincide con key_reference del envelope")
        return authenticate_envelope(envelope, object_value, active_key.key)
