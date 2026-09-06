"""Provider-neutral candidate discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CandidateProviderType(StrEnum):
    """Stable identities for candidate discovery strategies."""

    FOLLOWERS = "Followers"
    SPECIFIC_ACCOUNTS = "SpecificAccounts"


class CandidateResultStatus(StrEnum):
    """Structured outcomes returned to an interaction module."""

    CANDIDATE_FOUND = "CANDIDATE_FOUND"
    CURRENT_SOURCE_EXHAUSTED = "CURRENT_SOURCE_EXHAUSTED"
    ALL_SOURCES_EXHAUSTED = "ALL_SOURCES_EXHAUSTED"
    SCROLL_BLOCK = "SCROLL_BLOCK"
    FILTER_REJECTED = "FILTER_REJECTED"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One Instagram account discovered for a possible interaction."""

    username: str
    source: str
    provider_type: CandidateProviderType
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.username.strip():
            raise ValueError("Candidate username cannot be empty")
        if not self.source.strip():
            raise ValueError("Candidate source cannot be empty")


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """One candidate-provider outcome with no scheduler side effects."""

    status: CandidateResultStatus
    candidate: Candidate | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        found = self.status is CandidateResultStatus.CANDIDATE_FOUND
        if found != (self.candidate is not None):
            raise ValueError(
                "CANDIDATE_FOUND requires a candidate and other statuses forbid one"
            )


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    """Raw account identity returned by a platform discovery boundary."""

    username: str
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class FollowersDiscoverySettings:
    """Scrolling policy supplied by module-owned configuration."""

    scrolling_timeout_seconds: int
    use_random_search_letters: bool = False
    first_character_pool: str = ""
    second_character_pool: str = ""

    def __post_init__(self) -> None:
        if self.scrolling_timeout_seconds <= 0:
            raise ValueError("Scrolling timeout must be positive")


class DiscoveryStatus(StrEnum):
    """Outcomes internal to a platform discovery boundary."""

    ACCOUNT_FOUND = "ACCOUNT_FOUND"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SCROLL_BLOCK = "SCROLL_BLOCK"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """One platform discovery observation."""

    status: DiscoveryStatus
    observation: CandidateObservation | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        found = self.status is DiscoveryStatus.ACCOUNT_FOUND
        if found != (self.observation is not None):
            raise ValueError(
                "ACCOUNT_FOUND requires an observation and other statuses forbid one"
            )
