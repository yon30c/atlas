"""Puerto confiable para verificar evidencia de autorización de operaciones."""

from datetime import datetime
from typing import Protocol

from atlas.authorization.models import AuthorizationRequest
from atlas.authorization.operation_models import OperationAuthorizationEvidence


class OperationAuthorizationEvidenceVerifierPort(Protocol):
    """Verifica autenticidad y vigencia contra el estado autoritativo de CAM.

    La implementación debe comprobar, como mínimo:
    - que evidence fue emitida por un issuer CAM confiable y no fue alterada;
    - que decision_id/evidence_id corresponden a una decisión ALLOW auténtica;
    - que el actor y su revisión siguen activos y actuales;
    - que el Grant exacto existe, mantiene grant_revision, sigue vigente y no
      está revocado;
    - que proyecto y entorno siguen activos y en las revisiones aplicables;
    - que la solicitud coincide exactamente con la decisión emitida.

    Una lectura puntual sin garantías contra cambios concurrentes no basta
    para autorizar una ejecución con efectos. Si no puede demostrar estado
    autoritativo actual, debe devolver False o elevar una excepción.
    """

    def verify(
        self,
        request: AuthorizationRequest,
        evidence: OperationAuthorizationEvidence,
        now: datetime,
    ) -> bool:
        """True solo si toda la evidencia y autoridad actual son válidas."""
