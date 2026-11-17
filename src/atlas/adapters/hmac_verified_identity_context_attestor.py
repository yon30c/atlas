"""HMAC-SHA256 attestor for short-lived VerifiedIdentityContext claims."""

import base64
import hashlib
import hmac

from atlas.core.errors import ContractError


class HmacVerifiedIdentityContextAttestor:
    """Uses a server-held key shared by trusted Atlas workers.

    Key provisioning and rotation belong to the composition root. The key is
    never stored in the context, database, logs, or caller-controlled input.
    """

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise ContractError("la clave HMAC debe contener al menos 256 bits")
        self._key = bytes(key)

    def sign(self, payload: bytes) -> str:
        if not isinstance(payload, bytes):
            raise ContractError("payload HMAC debe ser bytes")
        digest = hmac.new(self._key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def verify(self, payload: bytes, attestation: str) -> bool:
        if not isinstance(payload, bytes) or not isinstance(attestation, str):
            return False
        try:
            supplied = base64.urlsafe_b64decode(attestation + "=")
        except (ValueError, base64.binascii.Error):
            return False
        if len(supplied) != hashlib.sha256().digest_size:
            return False
        expected = hmac.new(self._key, payload, hashlib.sha256).digest()
        return hmac.compare_digest(expected, supplied)
