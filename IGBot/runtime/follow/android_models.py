"""Android-specific Follow navigation and execution outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from IGBot.runtime.follow.models import CandidateProfile


class AndroidFollowStatus(StrEnum):
    """Outcomes emitted by AndroidFollowProvider operations."""

    SUCCESS = "SUCCESS"
    REQUESTED = "REQUESTED"
    ALREADY_FOLLOWING = "ALREADY_FOLLOWING"
    FOLLOW_BACK = "FOLLOW_BACK"
    PRIVATE_SKIPPED = "PRIVATE_SKIPPED"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    CONTACT_SCRAPED = "CONTACT_SCRAPED"
    CONTACT_NOT_AVAILABLE = "CONTACT_NOT_AVAILABLE"
    GHOST_BLOCK_DETECTED = "GHOST_BLOCK_DETECTED"
    FOLLOW_FAILED = "FOLLOW_FAILED"


@dataclass(frozen=True, slots=True)
class AndroidFollowResult:
    """One Android UI operation result with optional observed data."""

    status: AndroidFollowStatus
    detail: str | None = None
    profile: CandidateProfile | None = None
    contact_details: Mapping[str, str] = field(default_factory=dict)
