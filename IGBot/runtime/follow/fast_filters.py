"""Early keyword matching on rows; alphabet checks on literal subtitles only."""

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.models import TextFilterSettings
from IGBot.runtime.follow.qualifier import ConfiguredFollowCandidateQualifier


class FollowFastFilters:
    """Reuse profile matching semantics without requiring profile navigation."""

    def __init__(
        self,
        *,
        allowed_alphabets: tuple[str, ...] = (),
        blocked_words: tuple[str, ...] = (),
        required_words: tuple[str, ...] = (),
        only_active_stories: bool = False,
    ) -> None:
        self._allowed_alphabets = allowed_alphabets
        self._blocked = TextFilterSettings(blocked=blocked_words)
        self._required = TextFilterSettings(required=required_words)
        self._only_active_stories = only_active_stories

    def accepts(
        self,
        context: RuntimeContext,
        subtitle: str,
        username: str = "",
        *,
        has_active_story: bool = False,
    ) -> bool:
        rules = ConfiguredFollowCandidateQualifier
        if rules._unsupported_script(subtitle, self._allowed_alphabets) is not None:
            context.logger.info("[FastFilter] Allowed alphabet rejected.")
            return False
        combined = rules._normalize(f"{username} {subtitle}")
        if rules._keyword_rejection(combined, self._blocked) is not None:
            context.logger.info("[FastFilter] Blocked keyword detected.")
            return False
        if self._only_active_stories:
            if not has_active_story:
                context.logger.info(
                    "[FastFilter] Active story required. Candidate skipped."
                )
                return False
            context.logger.info("[FastFilter] Active story detected.")
        if self.required_keyword_visible(combined):
            # A positive row match is not profile qualification. The caller
            # must still open the profile and run every existing profile check.
            return True
        # Missing keywords can appear in the biography; never reject here.
        return True

    def required_keyword_visible(self, normalized_text: str) -> bool:
        return bool(self._required.required) and (
            ConfiguredFollowCandidateQualifier._keyword_rejection(
                normalized_text, self._required
            )
            is None
        )
