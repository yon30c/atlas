"""Port for fencing pre-restart emitters at each registered delivery endpoint."""
from typing import Protocol

from atlas.memory.recovery import (
    RecoveryEndpointFenceReceipt,
    RecoveryEndpointFenceRequest,
)


class RecoveryEndpointFencerPort(Protocol):
    """Endpoint-specific fence boundary.

    The implementation must authenticate the endpoint and ensure that all
    emitters holding the previous admission generation are unable to commit
    further output before returning a positive receipt. Dispatch acceptance,
    timeout, lease expiry, or a local cancellation request is not confirmation.
    The returned receipt must bind every request field and be independently
    verified through TerminalReceiptVerifierPort.
    """

    def fence_endpoint(
        self,
        request: RecoveryEndpointFenceRequest,
    ) -> RecoveryEndpointFenceReceipt | None:
        """Return an exact positive fence receipt, or None when not proven."""
