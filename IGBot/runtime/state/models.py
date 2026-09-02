"""Shared, side-effect-free runtime state objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar


class RuntimeState(StrEnum):
    """State of the native runtime as a whole."""

    STOPPED = "Stopped"
    STARTING = "Starting"
    RUNNING = "Running"
    STOPPING = "Stopping"
    ERROR = "Error"


class PhoneState(StrEnum):
    """State of one phone-level scheduler."""

    STOPPED = "Stopped"
    STARTING = "Starting"
    WAITING = "Waiting"
    RUNNING = "Running"
    STOPPING = "Stopping"
    ERROR = "Error"


class AccountState(StrEnum):
    """Runtime availability of an account outside an individual session."""

    IDLE = "Idle"
    QUEUED = "Queued"
    ACTIVE = "Active"
    PAUSED = "Paused"
    BLOCKED = "Blocked"
    ERROR = "Error"


class SessionState(StrEnum):
    """Lifecycle state of one account session."""

    PENDING = "Pending"
    STARTING = "Starting"
    RUNNING = "Running"
    PAUSED = "Paused"
    RECOVERING = "Recovering"
    STOPPING = "Stopping"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class ModuleState(StrEnum):
    """Availability of an interaction module within a session."""

    DISABLED = "Disabled"
    READY = "Ready"
    RUNNING = "Running"
    COOLING_DOWN = "CoolingDown"
    LIMIT_REACHED = "LimitReached"
    BLOCKED = "Blocked"
    FAILED = "Failed"


class HookState(StrEnum):
    """Lifecycle state of one runtime-hook invocation."""

    TRIGGERED = "Triggered"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


StateType = TypeVar("StateType", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class StateTransition(Generic[StateType]):
    """An observable transition emitted by a future runtime implementation."""

    previous: StateType
    current: StateType
    occurred_at: datetime
    reason: str | None = None
