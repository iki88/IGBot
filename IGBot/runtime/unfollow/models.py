"""Structured Unfollow runtime values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AndroidUnfollowStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_CANDIDATES = "NO_CANDIDATES"
    SEARCH_FAILED = "SEARCH_FAILED"
    PROFILE_MISMATCH = "PROFILE_MISMATCH"
    NOT_FOLLOWING = "NOT_FOLLOWING"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"


@dataclass(frozen=True, slots=True)
class AndroidUnfollowResult:
    status: AndroidUnfollowStatus
    detail: str | None = None
    username: str | None = None


@dataclass(frozen=True, slots=True)
class UnfollowSettings:
    enabled: bool
    configured: bool
    budget: int | str
    daily_remaining: int
    hourly_remaining: int
    delay_days: int
    require_no_follow_back: bool = False
