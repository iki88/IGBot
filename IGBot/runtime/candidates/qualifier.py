"""Shared candidate qualification workflow."""

from __future__ import annotations

from IGBot.runtime.candidates.contracts import (
    CandidateFilter,
    CandidateProfileReader,
)
from IGBot.runtime.candidates.models import (
    Candidate,
    CandidateResult,
    CandidateResultStatus,
)
from IGBot.runtime.context import RuntimeContext


class CandidateQualifier:
    """Apply visible filters before optional profile biography filters."""

    def __init__(
        self,
        candidate_filter: CandidateFilter,
        profile_reader: CandidateProfileReader,
    ) -> None:
        self._candidate_filter = candidate_filter
        self._profile_reader = profile_reader

    def qualify(self, context: RuntimeContext, candidate: Candidate) -> CandidateResult:
        """Return a found candidate or a structured filter rejection."""

        if not self._candidate_filter.accepts_visible(context, candidate):
            return CandidateResult(
                CandidateResultStatus.FILTER_REJECTED,
                detail=f"Visible filters rejected {candidate.username}.",
            )
        if self._candidate_filter.biography_required:
            biography = self._profile_reader.biography(context, candidate.username)
            if biography is None or not self._candidate_filter.accepts_biography(
                context, candidate, biography
            ):
                return CandidateResult(
                    CandidateResultStatus.FILTER_REJECTED,
                    detail=f"Biography filters rejected {candidate.username}.",
                )
        return CandidateResult(
            CandidateResultStatus.CANDIDATE_FOUND, candidate=candidate
        )
