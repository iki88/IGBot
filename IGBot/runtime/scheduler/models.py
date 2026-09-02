"""Side-effect-free scheduler inputs and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LimitScope(StrEnum):
    """Supported accounting windows for interaction limits."""

    SESSION = "Session"
    DAILY = "Daily"
    HOURLY = "Hourly"


@dataclass(frozen=True, slots=True)
class ModuleBudget:
    """Current scheduler budget for one enabled interaction module."""

    module: str
    session_remaining: int
    daily_remaining: int
    hourly_remaining: int
    priority: int = 0


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    """A strategy decision; execution remains the controller's responsibility."""

    module: str | None
    reason: str
