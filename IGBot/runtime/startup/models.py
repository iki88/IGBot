"""Structured inputs and outcomes for Session Startup."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StartupStageName(StrEnum):
    """Stable names for the ordered startup stages."""

    INTERNET = "Internet"
    AIRPLANE_MODE = "AirplaneMode"
    INSTAGRAM_LAUNCH = "InstagramLaunch"
    WAIT_AFTER_LAUNCH = "WaitAfterLaunch"
    ACCOUNT_VERIFICATION = "AccountVerification"
    FOLLOWER_SYNCHRONIZATION = "FollowerSynchronization"


class StartupStageStatus(StrEnum):
    """The only outcomes a startup stage may return."""

    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class StartupStageResult:
    """Result of one startup stage, including optional scheduler facts."""

    stage: StartupStageName
    status: StartupStageStatus
    detail: str | None = None
    internet_available: bool | None = None
    account_verified: bool | None = None
    new_followers_found: int | None = None

    def __post_init__(self) -> None:
        if self.new_followers_found is not None and self.new_followers_found < 0:
            raise ValueError("new_followers_found cannot be negative")


@dataclass(frozen=True, slots=True)
class StartupResult:
    """Immutable handoff from Session Startup to the scheduler."""

    startup_completed: bool
    internet_available: bool | None
    account_verified: bool | None
    new_followers_found: int
    startup_failed: bool
    stage_results: tuple[StartupStageResult, ...]
    failure_reason: str | None = None
