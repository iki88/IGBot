"""Native Welcome-DM settings and Android outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from IGBot.runtime.navigation import NavigationResult


class AndroidDMStatus(StrEnum):
    SUCCESS = "SUCCESS"
    SEARCH_FAILED = "SEARCH_FAILED"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    PROFILE_UNAVAILABLE = "PROFILE_UNAVAILABLE"
    MESSAGE_BUTTON_NOT_FOUND = "MESSAGE_BUTTON_NOT_FOUND"
    THREAD_FAILED = "THREAD_FAILED"
    TYPE_FAILED = "TYPE_FAILED"
    SEND_FAILED = "SEND_FAILED"
    IGNORED = "IGNORED"


@dataclass(frozen=True, slots=True)
class AndroidDMResult:
    status: AndroidDMStatus
    detail: str | None = None
    navigation: NavigationResult = field(default_factory=NavigationResult)


@dataclass(frozen=True, slots=True)
class DMSettings:
    enabled: bool
    configured: bool
    message: str
    budget: int | str = 1
    daily_remaining: int = 0
    hourly_remaining: int = 0
    action_delay: int | str = 0
