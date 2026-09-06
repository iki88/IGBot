"""Provider-neutral boundaries used by the Follow preparation workflow."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.candidates import Candidate
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.models import (
    CandidateProfile,
    FollowFilterSettings,
    FollowQualificationResult,
)


class CandidateProfileProvider(Protocol):
    """Open a discovered candidate and read Follow qualification facts."""

    def open_profile(
        self, context: RuntimeContext, candidate: Candidate
    ) -> CandidateProfile | None:
        """Return the opened profile or None when it cannot be inspected."""
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
