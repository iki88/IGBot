"""Structured Instagram profile observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProfileObservationState(StrEnum):
    """Outcomes available after navigating to the Instagram profile."""

    USERNAME_VISIBLE = "USERNAME_VISIBLE"
    USERNAME_TRUNCATED = "USERNAME_TRUNCATED"
    PROFILE_NOT_AVAILABLE = "PROFILE_NOT_AVAILABLE"
    PROFILE_NOT_LOADED = "PROFILE_NOT_LOADED"


@dataclass(frozen=True, slots=True)
class ProfileObservation:
    """Visible profile state returned by a platform provider."""

    state: ProfileObservationState
    username: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class UsernameDetectionResult:
    """Complete username read from the selected Account Switcher row."""

    username: str | None = None
    detail: str | None = None
