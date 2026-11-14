"""Write-side port for immutable checkpoint projection artifacts.

The publisher is deliberately separate from the SQLite journal and from the
resolver used during recovery. Implementations must durably publish and read
back both content-addressed objects before returning successfully.
"""
from typing import Protocol

from atlas.memory.checkpoint_projection_codec import CheckpointProjectionArtifacts


class LocalCheckpointProjectionPublisherPort(Protocol):
    """Publish immutable projection state and its integrity manifest."""

    def publish_checkpoint_projection(
        self, artifacts: CheckpointProjectionArtifacts
    ) -> None:
        """Persist state first, then manifest, and verify both by read-back.

        A failure may leave an unreferenced immutable state object. It must
        never expose success until both objects are durable and verified.
        Existing objects may be reused only when their bytes match exactly.
        """
