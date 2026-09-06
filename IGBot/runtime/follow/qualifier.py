"""Follow-specific candidate qualification."""

from __future__ import annotations

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.models import (
    CandidateProfile,
    FollowFilterSettings,
    FollowModuleResultStatus,
    FollowQualificationResult,
    TextFilterSettings,
)


class ConfiguredFollowCandidateQualifier:
    """Apply username, name, biography, and private-profile settings."""

    def qualify(
        self,
        context: RuntimeContext,
        profile: CandidateProfile,
        settings: FollowFilterSettings,
    ) -> FollowQualificationResult:
        """Qualify one opened profile without modifying runtime state."""

        del context
        if profile.is_private and not settings.allow_private:
            return FollowQualificationResult(
                FollowModuleResultStatus.PRIVATE_SKIPPED,
                "Private profile is disabled by Follow settings.",
            )
        fields = (
            ("username", profile.username, settings.username),
            ("name", profile.display_name, settings.display_name),
            ("biography", profile.biography, settings.biography),
        )
        for label, value, rule in fields:
            if not self._accepts(value, rule):
                return FollowQualificationResult(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    f"Candidate {label} was rejected by Follow filters.",
                )
        return FollowQualificationResult(FollowModuleResultStatus.READY_TO_FOLLOW)

    @staticmethod
    def _accepts(value: str, settings: TextFilterSettings) -> bool:
        normalized = value.casefold()
        required = tuple(item.casefold() for item in settings.required if item)
        blocked = tuple(item.casefold() for item in settings.blocked if item)
        return (
            not required or any(item in normalized for item in required)
        ) and not any(item in normalized for item in blocked)
