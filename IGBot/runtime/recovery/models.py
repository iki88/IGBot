"""Requests and decisions used at the failure-recovery boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from IGBot.runtime.context import RuntimeContext


class FailureKind(StrEnum):
    """Failure classes defined by the runtime architecture."""

    INSTAGRAM_CRASH = "InstagramCrash"
    ACTION_BLOCK = "ActionBlock"
    LOGIN_FAILURE = "LoginFailure"
    DEVICE_FAILURE = "DeviceFailure"
    AUTOMATION_FAILURE = "AutomationFailure"


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    """Failure context passed to the recovery subsystem."""

    context: RuntimeContext
    failure: FailureKind
    detail: str
    attempt: int


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """A recovery policy decision without embedded recovery behaviour."""

    retry: bool
    pause_account: bool
    reason: str
