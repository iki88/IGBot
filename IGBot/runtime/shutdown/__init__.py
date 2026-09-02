"""Session-finalization contracts."""

from IGBot.runtime.shutdown.contracts import ShutdownController, StatisticsUploader
from IGBot.runtime.shutdown.models import (
    ShutdownReason,
    ShutdownRequest,
    ShutdownResult,
)

__all__ = [
    "ShutdownController",
    "ShutdownReason",
    "ShutdownRequest",
    "ShutdownResult",
    "StatisticsUploader",
]
