"""Contracts for session finalization and statistics upload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.shutdown.models import ShutdownRequest, ShutdownResult


class StatisticsUploader(Protocol):
    """Upload final statistics through an external integration boundary."""

    def upload(self, context: RuntimeContext, statistics: Mapping[str, int]) -> None:
        """Upload statistics for a completed session."""
        ...


class ShutdownController(Protocol):
    """Coordinate the final, once-per-session shutdown stage."""

    def finalize(self, request: ShutdownRequest) -> ShutdownResult:
        """Finalize a session and return the observable outcome."""
        ...
