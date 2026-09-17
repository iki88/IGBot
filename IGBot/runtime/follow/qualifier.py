"""Follow-specific candidate qualification."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow.models import (
    CandidateProfile,
    FollowFilterSettings,
    FollowModuleResultStatus,
    FollowQualificationResult,
    TextFilterSettings,
)


class ConfiguredFollowCandidateQualifier:
    """Apply the ordered, provider-neutral Follow qualification pipeline."""

    _SCRIPT_PATTERN = re.compile(
        r"(?P<LATIN>[A-Za-z\u00c0-\u024f\u1e00-\u1eff\uab30-\uab6f])|"
        r"(?P<CYRILLIC>[\u0400-\u052f\u2de0-\u2dff\ua640-\ua69f])|"
        r"(?P<GREEK>[\u0370-\u03ff\u1f00-\u1fff])|"
        r"(?P<ARABIC>[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff"
        r"\ufb50-\ufdff\ufe70-\ufeff])|"
        r"(?P<HEBREW>[\u0590-\u05ff\ufb1d-\ufb4f])|"
        r"(?P<JAPANESE>[\u3040-\u30ff\u31f0-\u31ff])|"
        r"(?P<HAN>[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])|"
        r"(?P<KOREAN>[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af])|"
        r"(?P<THAI>[\u0e00-\u0e7f])|"
        r"(?P<HINDI>[\u0900-\u097f\ua8e0-\ua8ff])"
    )
    _CJK = frozenset({"JAPANESE", "CHINESE", "KOREAN"})

    def __init__(self, language_detector: Callable[[str], str] | None = None) -> None:
        self._language_detector = language_detector or self._detect_language

    def qualify(
        self,
        context: RuntimeContext,
        profile: CandidateProfile,
        settings: FollowFilterSettings,
    ) -> FollowQualificationResult:
        """Qualify one already-scraped profile without modifying runtime state."""

        if profile.is_private and not settings.allow_private:
            context.logger.info("[Filter] Private profile skipped.")
            return FollowQualificationResult(
                FollowModuleResultStatus.PRIVATE_SKIPPED,
                "Private profile is disabled by Follow settings.",
            )
        context.logger.debug(
            "[Filter] Verified profile state evaluated.",
            verified=profile.is_verified,
        )

        if profile.is_business:
            context.logger.info(
                "[Filter] Business profile detected.", category=profile.category
            )
            if settings.skip_business:
                context.logger.info("[Filter] Business profile skipped.")
                return FollowQualificationResult(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    "Business profile is disabled by Follow settings.",
                )

        if settings.skip_link_in_bio and profile.has_external_links:
            context.logger.info("[Filter] Link in Bio detected. Candidate skipped.")
            return FollowQualificationResult(
                FollowModuleResultStatus.FILTER_REJECTED,
                "Profile exposes one or more external links.",
            )

        numeric_filters = (
            (
                "followers",
                profile.followers,
                settings.min_followers,
                settings.max_followers,
            ),
            (
                "following",
                profile.following,
                settings.min_following,
                settings.max_following,
            ),
            ("posts", profile.posts, settings.min_posts, None),
        )
        for label, value, minimum, maximum in numeric_filters:
            rejection = self._number_rejection(label, value, minimum, maximum)
            if rejection is not None:
                context.logger.info(f"[Filter] {rejection}")
                return FollowQualificationResult(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    rejection,
                )

        combined = self._normalize(
            f"{profile.username} {profile.display_name} "
            f"{profile.biography} {profile.category}"
        )
        keyword_settings = self._combined_text_settings(settings)
        keyword_rejection = self._keyword_rejection(combined, keyword_settings)
        if keyword_rejection is not None:
            context.logger.info(f"[Filter] {keyword_rejection}")
            return FollowQualificationResult(
                FollowModuleResultStatus.FILTER_REJECTED,
                keyword_rejection,
            )
        if keyword_settings.required or keyword_settings.blocked:
            context.logger.info("[Filter] Keyword filter matched.")

        unsupported = self._unsupported_script(
            f"{profile.display_name} {profile.biography}",
            settings.allowed_alphabets,
        )
        if unsupported is not None:
            context.logger.info(
                f"[Filter] Unsupported alphabet detected ({unsupported}). "
                "Candidate rejected."
            )
            return FollowQualificationResult(
                FollowModuleResultStatus.FILTER_REJECTED,
                f"Candidate uses unsupported alphabet: {unsupported}.",
            )
        if settings.allowed_alphabets:
            context.logger.info("[Filter] Allowed alphabet check passed.")

        allowed_languages = self._languages(settings.biography_languages)
        if not allowed_languages:
            context.logger.debug(
                "[Filter] Biography language detection skipped "
                "(no configured languages)."
            )
        else:
            language_text = " ".join(
                value for value in (profile.display_name, profile.biography) if value
            ).strip()
            try:
                detected = self._language_detector(language_text).casefold()
            except Exception as error:  # noqa: BLE001 - language detector boundary
                return FollowQualificationResult(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    f"Biography language could not be detected: {error}",
                )
            context.logger.info(
                "[Filter] Biography language detected.", language=detected
            )
            if detected not in allowed_languages:
                context.logger.info(
                    "[Filter] Biography language not allowed. Candidate rejected.",
                    detected=detected,
                    allowed=", ".join(sorted(allowed_languages)),
                )
                return FollowQualificationResult(
                    FollowModuleResultStatus.FILTER_REJECTED,
                    f"Biography language was rejected: {detected}.",
                )

        context.logger.info("[Filter] Candidate passed all filters.")
        return FollowQualificationResult(FollowModuleResultStatus.READY_TO_FOLLOW)

    @classmethod
    def _unsupported_script(cls, text: str, configured: tuple[str, ...]) -> str | None:
        if not configured:
            return None
        allowed = {
            (
                "HINDI"
                if value.strip().casefold() == "devanagari"
                else value.strip().upper()
            )
            for value in configured
            if value.strip()
        }
        for character in text:
            match = cls._SCRIPT_PATTERN.fullmatch(character)
            if match is not None:
                script = str(match.lastgroup)
                if script == "HAN":
                    if not (allowed & cls._CJK):
                        return "Chinese"
                elif script not in allowed:
                    return script.title()
            elif unicodedata.category(character).startswith("L"):
                return unicodedata.name(character, "Unknown").split(" ", 1)[0].title()
        return None

    @staticmethod
    def _number_rejection(
        label: str,
        value: int | None,
        minimum: int | None,
        maximum: int | None,
    ) -> str | None:
        if minimum is None and maximum is None:
            return None
        if value is None:
            return f"{label.title()} count unavailable. Candidate skipped."
        if minimum is not None and value < minimum:
            return f"Minimum {label} not satisfied. Candidate skipped."
        if maximum is not None and value > maximum:
            return f"Maximum {label} exceeded. Candidate skipped."
        return None

    @staticmethod
    def _combined_text_settings(settings: FollowFilterSettings) -> TextFilterSettings:
        rules = (
            settings.keywords,
            settings.username,
            settings.display_name,
            settings.biography,
        )
        return TextFilterSettings(
            required=tuple(item for rule in rules for item in rule.required),
            blocked=tuple(item for rule in rules for item in rule.blocked),
        )

    @classmethod
    def _keyword_rejection(
        cls, normalized: str, settings: TextFilterSettings
    ) -> str | None:
        required = tuple(cls._normalize(item) for item in settings.required if item)
        blocked = tuple(cls._normalize(item) for item in settings.blocked if item)
        matched_blocked = next((item for item in blocked if item in normalized), None)
        if matched_blocked is not None:
            return f"Blocked keyword matched ({matched_blocked}). Candidate skipped."
        if required and not any(item in normalized for item in required):
            return "Required keyword not found. Candidate skipped."
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    @staticmethod
    def _languages(values: tuple[str, ...]) -> frozenset[str]:
        return frozenset(
            value.strip().casefold().split("-", 1)[0]
            for value in values
            if value.strip()
        )

    @staticmethod
    def _detect_language(text: str) -> str:
        if not text:
            raise ValueError("profile name and biography are empty")
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        return detect(text)
