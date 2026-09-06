"""Contracts for candidate discovery, filtering, and profile inspection."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.candidates.models import (
    Candidate,
    CandidateObservation,
    CandidateResult,
    DiscoveryResult,
    FollowersDiscoverySettings,
)
from IGBot.runtime.context import RuntimeContext


class CandidateProvider(Protocol):
    """Discover candidates for one interaction module without interacting."""

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        """Return the next provider outcome."""
        ...


class CandidateFilter(Protocol):
    """Apply module-owned qualification rules to discovered accounts."""

    @property
    def biography_required(self) -> bool:
        """Return whether accepted visible candidates require a biography read."""
        ...

    def accepts_visible(self, context: RuntimeContext, candidate: Candidate) -> bool:
        """Apply filters available from the source surface."""
        ...

    def accepts_biography(
        self,
        context: RuntimeContext,
        candidate: Candidate,
        biography: str,
    ) -> bool:
        """Apply biography rules after an explicit profile read."""
        ...


class CandidateProfileReader(Protocol):
    """Read profile data needed by an enabled filter."""

    def biography(self, context: RuntimeContext, username: str) -> str | None:
        """Open the profile and return its biography when available."""
        ...


class FollowersDiscovery(Protocol):
    """Platform boundary for follower-list navigation and reading."""

    def open_source(self, context: RuntimeContext, source: str) -> bool:
        """Open a configured source account's followers list."""
        ...

    def next_follower(
        self,
        context: RuntimeContext,
        source: str,
        settings: FollowersDiscoverySettings,
    ) -> DiscoveryResult:
        """Read one account using the supplied scrolling policy."""
        ...


class SpecificAccountDiscovery(Protocol):
    """Platform boundary for opening one configured username."""

    def open_account(
        self, context: RuntimeContext, username: str
    ) -> CandidateObservation | None:
        """Open and observe the configured account."""
        ...
