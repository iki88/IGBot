"""Provider-neutral boundaries used by the Follow preparation workflow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

from IGBot.runtime.candidates import Candidate
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.models import (
    CandidateProfile,
    FollowFilterSettings,
    FollowQualificationResult,
)

if TYPE_CHECKING:
    from IGBot.runtime.follow.android_models import AndroidFollowResult


class CandidateProfileProvider(Protocol):
    """Open a discovered candidate and read Follow qualification facts."""

    def open_profile(
        self, context: RuntimeContext, candidate: Candidate
    ) -> CandidateProfile | None:
        """Return the opened profile or None when it cannot be inspected."""
        ...

    def return_to_followers(self, context: RuntimeContext) -> AndroidFollowResult:
        """Restore the Followers list after a non-fatal candidate rejection."""
        ...


class FollowCandidateQualifier(Protocol):
    """Apply Follow-owned filters to one opened candidate profile."""

    def qualify(
        self,
        context: RuntimeContext,
        profile: CandidateProfile,
        settings: FollowFilterSettings,
    ) -> FollowQualificationResult:
        """Return a structured qualification result without side effects."""
        ...


class ContactScraper(Protocol):
    """Extract contact values from an already-open Android hierarchy."""

    def scrape(self, context: RuntimeContext, hierarchy: str) -> Mapping[str, str]:
        """Return observed contact fields without navigation or persistence."""
        ...


class FollowInteractionProvider(Protocol):
    """Execute a runtime-authorized Follow through a platform UI."""

    def execute_follow(self, context: RuntimeContext) -> AndroidFollowResult:
        """Execute and verify one Follow, then restore source navigation."""
        ...
