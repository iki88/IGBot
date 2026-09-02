"""Provider-neutral requests and results for the compatibility boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from IGBot.runtime.context import RuntimeContext


class ExecutionStatus(StrEnum):
    """Provider-neutral execution outcomes."""

    COMPLETED = "Completed"
    STOPPED = "Stopped"
    FAILED = "Failed"


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """One scheduler-approved module execution request."""

    context: RuntimeContext
    module: str
    budget: int
    settings: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Provider-neutral result returned to the smart scheduler."""

    status: ExecutionStatus
    completed_actions: int
    detail: str | None = None
