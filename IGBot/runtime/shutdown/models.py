"""Inputs and outcomes for final session shutdown."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from IGBot.runtime.context import RuntimeContext


class ShutdownReason(StrEnum):
    """Reasons an account session can enter finalization."""

    COMPLETED = "Completed"
    OPERATOR_STOP = "OperatorStop"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass(frozen=True, slots=True)
class ShutdownRequest:
    """Data required to finalize one session."""

    context: RuntimeContext
    reason: ShutdownReason
    statistics: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ShutdownResult:
    """Observable result of future shutdown orchestration."""

    finalized: bool
    detail: str | None = None
