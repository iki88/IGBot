"""Structured configuration and outcomes for Follow preparation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from IGBot.runtime.candidates import Candidate
from IGBot.runtime.hooks import HookResult


class FollowModuleResultStatus(StrEnum):
    """Follow workflow outcomes before an interaction is attempted."""

    READY_TO_FOLLOW = "READY_TO_FOLLOW"
    FILTER_REJECTED = "FILTER_REJECTED"
    PRIVATE_SKIPPED = "PRIVATE_SKIPPED"
    NO_CANDIDATES = "NO_CANDIDATES"
    SCROLL_BLOCK = "SCROLL_BLOCK"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class TextFilterSettings:
    """Case-insensitive required and blocked text fragments."""

    required: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FollowFilterSettings:
    """Profile qualification settings owned by the Follow Module."""

    username: TextFilterSettings = TextFilterSettings()
    display_name: TextFilterSettings = TextFilterSettings()
    biography: TextFilterSettings = TextFilterSettings()
    allow_private: bool = False
    skip_business: bool = False
    skip_link_in_bio: bool = False
    min_followers: int | None = None
    max_followers: int | None = None
    min_following: int | None = None
    max_following: int | None = None
    min_posts: int | None = None
    keywords: TextFilterSettings = TextFilterSettings()
    allowed_alphabets: tuple[str, ...] = ()
    biography_languages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FollowModuleSettings:
    """Validated session snapshot consumed by one Follow Module."""

    enabled: bool
    configured: bool
    budget: int | str
    daily_remaining: int
    hourly_remaining: int = 100_000
    filters: FollowFilterSettings = FollowFilterSettings()
    contact_scraping_enabled: bool = False
    follow_back_enabled: bool = False

    def __post_init__(self) -> None:
        if self.daily_remaining < 0:
            raise ValueError("Follow daily remaining cannot be negative")
        if self.hourly_remaining < 0:
            raise ValueError("Follow hourly remaining cannot be negative")


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    """Profile facts needed to prepare a Follow interaction."""

    candidate: Candidate
    username: str
    display_name: str = ""
    biography: str = ""
    is_private: bool = False
    category: str = ""
    website: str = ""
    address: str = ""
    followers: int | None = None
    following: int | None = None
    posts: int | None = None
    is_business: bool = False
    is_verified: bool = False
    follow_status: str = ""
    has_external_links: bool = False


@dataclass(frozen=True, slots=True)
class FollowQualificationResult:
    """Result of applying Follow-owned profile filters."""

    status: FollowModuleResultStatus
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.status not in (
            FollowModuleResultStatus.READY_TO_FOLLOW,
            FollowModuleResultStatus.FILTER_REJECTED,
            FollowModuleResultStatus.PRIVATE_SKIPPED,
        ):
            raise ValueError("Invalid Follow qualification status")


@dataclass(frozen=True, slots=True)
class FollowModuleResult:
    """Domain result attached to a scheduler ModuleExecutionResult."""

    status: FollowModuleResultStatus
    candidate: Candidate | None = None
    hook_results: tuple[HookResult, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        ready = self.status is FollowModuleResultStatus.READY_TO_FOLLOW
        if ready != (self.candidate is not None):
            raise ValueError(
                "READY_TO_FOLLOW requires a candidate and other statuses forbid one"
            )
