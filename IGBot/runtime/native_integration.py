"""Production composition boundary for the native IGBot runtime."""

from __future__ import annotations

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml

from IGBot.core.device import AssignedAccount
from IGBot.core.session_engine import SessionState as UiSessionState
from IGBot.runtime.account_verification import (
    AndroidInstagramProfileProvider,
    AndroidInstagramStateProvider,
)
from IGBot.runtime.airplane_mode import AndroidAirplaneModeProvider
from IGBot.runtime.application import AndroidApplicationProvider
from IGBot.runtime.candidates import (
    Candidate,
    CandidateObservation,
    CandidateProviderType,
    DiscoveryResult,
    DiscoveryStatus,
    FollowersDiscoverySettings,
    SpecificUsersProvider,
)
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.database import FollowRecord, RuntimeDatabase
from IGBot.runtime.database.timestamps import utc_timestamp
from IGBot.runtime.eligibility import follow_provider_is_configured
from IGBot.runtime.follow import (
    AndroidContactScraper,
    AndroidFollowProvider,
    AndroidFollowStatus,
    CandidateProfile,
    ConfiguredFollowCandidateQualifier,
    FollowFilterSettings,
    FollowModule,
    FollowModuleResultStatus,
    FollowModuleSettings,
    TextFilterSettings,
)
from IGBot.runtime.follow.daily_limits import remaining_daily_follows
from IGBot.runtime.follow.fast_filters import FollowFastFilters
from IGBot.runtime.follow.source_session import (
    FollowProviderSequence,
    FollowSourcesProvider,
    SourceSession,
)
from IGBot.runtime.follower_synchronization import (
    AndroidFollowerReader,
    FollowerSynchronization,
    RuntimeFollowerComparer,
    RuntimeFollowerWriter,
)
from IGBot.runtime.hooks import HookEventType, HookResult
from IGBot.runtime.network import AndroidNetworkProvider
from IGBot.runtime.profile_database import GlobalDatabaseWriter, ProfileUpdate
from IGBot.runtime.recent_apps import AndroidRecentAppsProvider
from IGBot.runtime.recovery import RecoveryDecision
from IGBot.runtime.scheduler import (
    BackoffPolicy,
    BudgetCalculator,
    ExecutionCoordinator,
    ModuleExecutionOutcome,
    ModuleExecutionResult,
    ModulePoolBuilder,
    ModuleSelector,
    Scheduler,
    SchedulerLoop,
)
from IGBot.runtime.session import SessionContext
from IGBot.runtime.session.controller import (
    SessionController as NativeSessionController,
)
from IGBot.runtime.startup import (
    AccountVerifier,
    AirplaneModeController,
    CloseRecentApps,
    InstagramLauncher,
    InstagramStateRecovery,
    InternetChecker,
    StartupPipeline,
)
from IGBot.services.global_settings_service import GlobalSettingsService

logger = logging.getLogger(__name__)
# RuntimeContext diagnostics must reach the existing root-attached Qt Live Log
# handler. Without an explicit level this child inherits Python's WARNING default.
logger.setLevel(logging.DEBUG)


class PythonRuntimeLogger:
    """Forward structured native-runtime events into the existing Live Log."""

    @staticmethod
    def _message(message: str, fields: Mapping[str, object]) -> str:
        suffix = " ".join(f"{key}={value}" for key, value in fields.items())
        return f"{message} ({suffix})" if suffix else message

    def debug(self, message: str, **fields: object) -> None:
        logger.debug(self._message(message, fields))

    def info(self, message: str, **fields: object) -> None:
        logger.info(self._message(message, fields))

    def warning(self, message: str, **fields: object) -> None:
        logger.warning(self._message(message, fields))

    def error(self, message: str, **fields: object) -> None:
        logger.error(self._message(message, fields))


class _LoggingNotifier:
    def notify(self, context: RuntimeContext, notification) -> None:
        context.logger.warning(notification.title, message=notification.message)


class _ProfilePersistence:
    def __init__(self, writer: GlobalDatabaseWriter) -> None:
        self._writer = writer
        self._profiles: dict[str, CandidateProfile] = {}

    def submit(
        self,
        profile: CandidateProfile,
        details: Mapping[str, str] | None = None,
    ) -> None:
        details = details or {}
        self._profiles[profile.username.casefold()] = profile
        self._writer.submit(
            ProfileUpdate(
                username=profile.username,
                full_name=profile.display_name,
                biography=profile.biography,
                category=profile.category,
                website=details.get("website", profile.website),
                phone=details.get("phone", ""),
                email=details.get("email", ""),
                address=details.get("address", profile.address),
                followers=profile.followers,
                following=profile.following,
                posts=profile.posts,
                is_private=profile.is_private,
                is_business=profile.is_business,
                is_verified=profile.is_verified,
                follow_status=profile.follow_status,
                source_account=profile.candidate.source,
                discovered_at=utc_timestamp(datetime.now(timezone.utc)),
            )
        )

    def mark_followed(self, username: str, status: str) -> None:
        profile = self._profiles.get(username.casefold())
        if profile is not None:
            self.submit(replace(profile, follow_status=status))

    def observe(self, _context: RuntimeContext, profile: CandidateProfile) -> None:
        self.submit(profile)


class _ProfileObservationHooks:
    """Scrape optional contacts and enqueue one shared profile observation."""

    def __init__(
        self,
        android: AndroidFollowProvider,
        persistence: _ProfilePersistence,
        *,
        contact_enabled: bool,
    ) -> None:
        self._android = android
        self._persistence = persistence
        self._contact_enabled = contact_enabled

    def dispatch(self, event) -> tuple[HookResult, ...]:
        if event.event_type is not HookEventType.PROFILE_OPENED:
            return ()
        profile = event.payload.get("profile")
        if not isinstance(profile, CandidateProfile):
            return (HookResult(False, "Profile observation was unavailable."),)

        details: Mapping[str, str] = {}
        if self._contact_enabled:
            contact = self._android.scrape_contact(event.context)
            if contact.status is AndroidFollowStatus.CONTACT_SCRAPED:
                details = contact.contact_details
            elif contact.status is AndroidFollowStatus.FOLLOW_FAILED:
                event.context.logger.warning(
                    "[Contact] Contact scraping failed.", detail=contact.detail or ""
                )

        self._persistence.submit(profile, details)
        return (HookResult(True, "Profile persistence queued."),)


class _RecoveryReporter:
    def recover(self, request) -> RecoveryDecision:
        request.context.logger.error(
            "Runtime recovery required",
            failure=request.failure.value,
            detail=request.detail,
        )
        return RecoveryDecision(False, True, request.detail)


class _AllowVisibleCandidates:
    biography_required = False

    def accepts_visible(self, _context, _candidate) -> bool:
        return True

    def accepts_biography(self, _context, _candidate, _biography: str) -> bool:
        return True


class _UnusedBiographyReader:
    def biography(self, _context, _username: str) -> str | None:
        return None


class AndroidFollowersDiscovery:
    """Adapt AndroidFollowProvider navigation to FollowersProvider discovery."""

    _USERNAME_IDS = frozenset(
        {
            "follow_list_username",
            "row_user_primary_name",
            "row_user_textview",
            "username_textview",
        }
    )
    _USERNAME = re.compile(r"[A-Za-z0-9._]{1,30}")

    def __init__(
        self,
        android: AndroidFollowProvider,
        *,
        following: bool = False,
        follow_back_enabled: bool = False,
        cancellation_requested: Callable[[], bool] = lambda: False,
        fast_filters: FollowFastFilters | None = None,
    ) -> None:
        self._android = android
        self._following = following
        self._follow_back_enabled = follow_back_enabled
        self._cancellation_requested = cancellation_requested
        self._fast_filters = fast_filters or FollowFastFilters()
        self._seen: set[str] = set()
        self._source_started = 0.0
        self.session = SourceSession()
        self._source_followers: int | None = None
        self._strategy_selected = False
        self._letter: str | None = None
        self._letter_had_rows = False
        self._letter_results_pending = False
        self._last_rows: tuple = ()
        self._last_see_more_hierarchy: str | None = None

    def open_source(self, context: RuntimeContext, source: str) -> bool:
        discovery = "Following" if self._following else "Followers"
        context.logger.info(f"[Source] Discovery: {discovery}")
        located = self._android.locate_source(context, source)
        if located.status is not AndroidFollowStatus.SUCCESS:
            return False
        nodes = self._android._nodes(
            self._android._device(context).dump_hierarchy(compressed=False)
        )
        count_ids = (
            self._android._FOLLOWING_COUNT_IDS
            if self._following
            else self._android._FOLLOWER_COUNT_IDS
        )
        self._source_followers = self._android._profile_count(nodes, count_ids)
        opened = (
            self._android.open_following(context)
            if self._following
            else self._android.open_followers(context)
        )
        if opened.status is not AndroidFollowStatus.SUCCESS:
            return False
        self._android.show_more_followers(context)
        self._seen.clear()
        self._source_started = time.monotonic()
        self.session = SourceSession()
        self._strategy_selected = False
        self._letter = None
        self._letter_had_rows = False
        self._letter_results_pending = False
        self._last_rows = ()
        self._last_see_more_hierarchy = None
        return True

    def next_follower(
        self,
        context: RuntimeContext,
        _source: str,
        settings: FollowersDiscoverySettings,
    ) -> DiscoveryResult:
        device = self._android._device(context)  # integration over one Android owner
        if not self._strategy_selected:
            count_label = "Following" if self._following else "Followers"
            context.logger.info(
                f"[Source] {count_label} detected: "
                + (
                    f"{self._source_followers:,}"
                    if self._source_followers is not None
                    else "unavailable"
                )
            )
            if self._following:
                self.session.letter_search = False
            else:
                self.session.choose_strategy(self._source_followers)
            self._strategy_selected = True
            context.logger.info(
                "[Source] Strategy: Letter Search"
                if self.session.letter_search
                else "[Source] Strategy: Scroll"
            )
        while True:
            if self._cancellation_requested():
                return DiscoveryResult(DiscoveryStatus.SOURCE_EXHAUSTED)
            if (
                self.session.letter_search
                and self._letter is None
                and not self._next_letter(context, settings, device)
            ):
                return DiscoveryResult(DiscoveryStatus.SOURCE_EXHAUSTED)
            if self.session.letter_search and self._letter_results_pending:
                rows, hierarchy = self._wait_letter_results(device)
                self._letter_results_pending = False
            else:
                hierarchy = device.dump_hierarchy(compressed=False)
                rows = self._follower_rows(hierarchy)
            if self.session.letter_search and rows:
                self._letter_had_rows = True
            result = self._visible_candidate(context, rows)
            if result is not None:
                return result
            if (
                self._has_see_more(hierarchy)
                and hierarchy != self._last_see_more_hierarchy
            ):
                self._last_see_more_hierarchy = hierarchy
                shown = self._android.show_more_followers(context)
                if shown.status is AndroidFollowStatus.SUCCESS:
                    continue
            if self._has_suggested_boundary(hierarchy):
                return DiscoveryResult(DiscoveryStatus.SOURCE_EXHAUSTED)
            elapsed = time.monotonic() - self._source_started
            if (
                not self.session.letter_search
                and elapsed >= settings.scrolling_timeout_seconds
            ):
                return DiscoveryResult(DiscoveryStatus.SOURCE_EXHAUSTED)
            if self.session.letter_search and (not rows or rows == self._last_rows):
                if not self._letter_had_rows:
                    self.session.failed_letters.add(self._letter)
                context.logger.info("[Search] Letter completed.")
                self._letter = None
                self._last_rows = ()
                continue
            self._last_rows = rows
            scrolled = self._android.scroll_followers(context)
            if scrolled.status is not AndroidFollowStatus.SUCCESS:
                if self.session.letter_search:
                    context.logger.info("[Search] Letter completed.")
                    self._letter = None
                    self._last_rows = ()
                    continue
                return DiscoveryResult(
                    DiscoveryStatus.SCROLL_BLOCK, detail=scrolled.detail
                )

    def _visible_candidate(self, context, rows):
        for username, button_state, subtitle, has_active_story in rows:
            normalized = username.casefold()
            if normalized in self._seen:
                continue
            self._seen.add(normalized)
            if button_state in {"message", "following", "requested"}:
                context.logger.info(
                    "[Candidate] Skipping already-followed account",
                    button=button_state.title(),
                    username=username,
                )
                continue
            if button_state == "follow back" and not self._follow_back_enabled:
                context.logger.info(
                    "[Candidate] Skipping Follow Back account",
                    button="Follow back",
                    username=username,
                )
                continue
            if button_state not in {"follow", "follow back"}:
                continue
            if not self._fast_filters.accepts(
                context,
                subtitle,
                username,
                has_active_story=has_active_story,
            ):
                continue
            return DiscoveryResult(
                DiscoveryStatus.ACCOUNT_FOUND,
                CandidateObservation(username=username, display_name=subtitle or None),
            )

        return None

    def _next_letter(self, context, settings, device) -> bool:
        context.logger.info("[Search] Returning to Search field.")
        search = self._restore_followers_search(device)
        if search is None:
            return False
        letter = self.session.next_letter(
            settings.first_character_pool, settings.second_character_pool
        )
        if letter is None:
            return False
        device.click(*search.center)
        device.send_keys("", clear=True)
        context.logger.info("[Search] Next Letter: " + letter)
        device.send_keys(letter, clear=True)
        self._android._wait()
        self._letter = letter
        self._letter_had_rows = False
        self._letter_results_pending = True
        self._last_rows = ()
        return True

    def _restore_followers_search(self, device):
        """Scroll toward the list top until its inspected search field is visible."""

        for _attempt in range(30):
            nodes = self._android._nodes(device.dump_hierarchy(compressed=False))
            search = self._android._find_by_id(
                nodes, self._android._FOLLOWER_SEARCH_IDS
            )
            if search is not None:
                return search
            container = self._android._find_scrollable(nodes)
            if container is not None:
                left, top, right, bottom = container.bounds
            else:
                try:
                    width, height = device.window_size()
                except (AttributeError, TypeError, ValueError):
                    return None
                left, top, right, bottom = 0, 0, width, height
            device.swipe(
                (left + right) // 2,
                top + 1,
                (left + right) // 2,
                bottom - 1,
                duration=0.1,
            )
            self._android._sleeper(0.1)
        return None

    def _wait_letter_results(
        self, device
    ) -> tuple[tuple[tuple[str, str, str, bool], ...], str]:
        """Do not confuse the transient empty search hierarchy with zero results."""

        deadline = self._android._clock() + 3.0
        hierarchy = "<hierarchy />"
        while not self._cancellation_requested():
            hierarchy = device.dump_hierarchy(compressed=False)
            rows = self._follower_rows(hierarchy)
            if rows:
                return rows, hierarchy
            remaining = deadline - self._android._clock()
            if remaining <= 0:
                return (), hierarchy
            self._android._sleeper(min(0.25, remaining))
        return (), hierarchy

    @classmethod
    def _follower_rows(cls, hierarchy: str) -> tuple[tuple[str, str, str, bool], ...]:
        root = ET.fromstring(hierarchy)
        values: list[tuple[str, str, str, bool]] = []
        for row in root.iter("node"):
            if cls._is_suggested_header(row):
                break
            if cls._suffix(row) != "follow_list_container":
                continue
            username = next(
                (
                    node.get("text", "").strip()
                    for node in row.iter("node")
                    if cls._suffix(node) in cls._USERNAME_IDS
                ),
                "",
            )
            button = next(
                (
                    node.get("text", "").strip().casefold()
                    for node in row.iter("node")
                    if cls._suffix(node) == "follow_list_row_large_follow_button"
                ),
                "",
            )
            if cls._USERNAME.fullmatch(username):
                subtitle = next(
                    (
                        node.get("text", "")
                        for node in row.iter("node")
                        if cls._suffix(node) == "follow_list_subtitle"
                    ),
                    "",
                )
                has_active_story = any(
                    cls._suffix(node) == "follow_list_user_imageview"
                    and node.get("class") == "android.view.View"
                    for node in row.iter("node")
                )
                values.append((username, button, subtitle, has_active_story))
        return tuple(values)

    @classmethod
    def _has_see_more(cls, hierarchy: str) -> bool:
        return any(
            cls._suffix(node) == "see_more_button"
            for node in ET.fromstring(hierarchy).iter("node")
        )

    @classmethod
    def _has_suggested_boundary(cls, hierarchy: str) -> bool:
        return any(
            cls._is_suggested_header(node)
            for node in ET.fromstring(hierarchy).iter("node")
        )

    @classmethod
    def _is_suggested_header(cls, node: ET.Element) -> bool:
        return (
            cls._suffix(node) == "row_header_textview"
            and node.get("text", "").strip().casefold() == "suggested for you"
        )

    @staticmethod
    def _suffix(node: ET.Element) -> str:
        return node.get("resource-id", "").rsplit("/", 1)[-1].casefold()


class _FollowModuleProvider:
    def __init__(
        self,
        configuration: Mapping[str, object],
        filters: Mapping[str, object],
        runtime_settings: Mapping[str, object],
        android: AndroidFollowProvider,
        profile_persistence: _ProfilePersistence,
        cancellation_requested=lambda: False,
    ) -> None:
        self._configuration = configuration
        self._filters = filters
        self._runtime_settings = runtime_settings
        self._android = android
        self._profile_persistence = profile_persistence
        self._cancellation_requested = cancellation_requested
        self._modules: dict[str, FollowModule] = {}

    def modules_for(self, context: RuntimeContext) -> Iterable[FollowModule]:
        key = str(context.session.session_id)
        if key not in self._modules:
            self._modules[key] = self._build(context)
        return (self._modules[key],)

    def _build(self, context: RuntimeContext) -> FollowModule:
        follower_sources = self._string_list(
            self._configuration.get("blogger-followers")
        )
        following_sources = self._string_list(
            self._configuration.get("blogger-following")
        )
        specific_enabled = self._enabled(self._configuration.get("blogger"))
        enabled = self._enabled(self._configuration.get("follow-percentage"))
        budget = self._configuration.get("follow-limit") or 1
        daily = remaining_daily_follows(
            context.session.account_directory,
            self._configuration.get("total-follows-limit"),
        )
        hourly = self._integer_limit(
            self._runtime_settings.get("maximum_follows_per_hour"),
            default=100_000,
        )
        if hourly == 0:
            hourly = 100_000
        discovery_settings = FollowersDiscoverySettings(
            scrolling_timeout_seconds=max(
                1,
                int(self._runtime_settings.get("maximum_source_scrolling_time") or 5)
                * 60,
            ),
            use_random_search_letters=bool(
                self._runtime_settings.get("use_random_search_letters")
            ),
            first_character_pool=str(
                self._runtime_settings.get("first_character_pool") or ""
            ),
            second_character_pool=str(
                self._runtime_settings.get("second_character_pool") or ""
            ),
        )
        follow_back_enabled = not self._truthy(
            self._filters.get("skip_follower"), default=True
        )
        if specific_enabled:
            candidates = SpecificUsersProvider(
                context.session.account_directory, self._android
            )
        else:
            fast_filters = FollowFastFilters(
                required_words=self._string_list(self._filters.get("mandatory_words")),
                allowed_alphabets=self._string_list(
                    self._filters.get("specific_alphabet")
                ),
                blocked_words=self._string_list(self._filters.get("blacklist_words")),
                only_active_stories=bool(
                    self._runtime_settings.get("only_active_stories")
                ),
            )
            providers = tuple(
                FollowSourcesProvider(
                    sources,
                    AndroidFollowersDiscovery(
                        self._android,
                        following=following,
                        follow_back_enabled=follow_back_enabled,
                        cancellation_requested=self._cancellation_requested,
                        fast_filters=fast_filters,
                    ),
                    _AllowVisibleCandidates(),
                    _UnusedBiographyReader(),
                    discovery_settings,
                )
                for sources, following in (
                    (follower_sources, False),
                    (following_sources, True),
                )
                if sources
            )
            if not providers:
                candidates = FollowSourcesProvider(
                    (),
                    AndroidFollowersDiscovery(self._android),
                    _AllowVisibleCandidates(),
                    _UnusedBiographyReader(),
                    discovery_settings,
                )
            elif len(providers) == 1:
                candidates = providers[0]
            else:
                candidates = FollowProviderSequence(providers)
        configured = follow_provider_is_configured(self._configuration)
        return FollowModule(
            context,
            FollowModuleSettings(
                enabled=enabled,
                configured=configured,
                budget=str(budget),
                daily_remaining=daily,
                hourly_remaining=hourly,
                filters=FollowFilterSettings(
                    allow_private=self._truthy(
                        self._filters.get("follow_private_or_empty")
                    ),
                    follow_only_private=self._truthy(
                        self._filters.get("follow_only_private")
                    ),
                    skip_business=self._truthy(self._filters.get("skip_business")),
                    follow_only_business=self._truthy(
                        self._filters.get("follow_only_business")
                    ),
                    skip_link_in_bio=self._truthy(
                        self._filters.get("skip_if_link_in_bio")
                    ),
                    follow_only_link_in_bio=self._truthy(
                        self._filters.get("follow_only_link_in_bio")
                    ),
                    min_followers=self._optional_integer(
                        self._filters.get("min_followers")
                    ),
                    max_followers=self._optional_integer(
                        self._filters.get("max_followers")
                    ),
                    min_following=self._optional_integer(
                        self._filters.get("min_followings")
                    ),
                    max_following=self._optional_integer(
                        self._filters.get("max_followings")
                    ),
                    min_posts=self._optional_integer(self._filters.get("min_posts")),
                    keywords=TextFilterSettings(
                        required=self._string_list(
                            self._filters.get("mandatory_words")
                        ),
                        blocked=self._string_list(self._filters.get("blacklist_words")),
                    ),
                    allowed_alphabets=self._string_list(
                        self._filters.get("specific_alphabet")
                    ),
                    biography_languages=self._string_list(
                        self._filters.get("biography_language")
                    ),
                ),
                contact_scraping_enabled=bool(
                    self._runtime_settings.get("enable_contact_details_scraping")
                ),
            ),
            candidates,
            self._android,
            ConfiguredFollowCandidateQualifier(),
            _ProfileObservationHooks(
                self._android,
                self._profile_persistence,
                contact_enabled=bool(
                    self._runtime_settings.get("enable_contact_details_scraping")
                ),
            ),
            cancellation_requested=self._cancellation_requested,
        )

    @staticmethod
    def _enabled(value: object) -> bool:
        return value not in (None, False, 0, "", "0")

    @staticmethod
    def _string_list(value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value.strip(),) if value.strip() else ()
        if isinstance(value, list):
            return tuple(str(item).strip() for item in value if str(item).strip())
        return ()

    @staticmethod
    def _integer_limit(value: object, *, default: int) -> int:
        try:
            return max(0, int(str(value).split("-", 1)[-1]))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_integer(value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _truthy(value: object, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().casefold() in {"1", "true", "yes", "on"}
        return bool(value)


class _NativeFollowExecutor:
    """Connect Follow preparation to the Android execution boundary."""

    def __init__(
        self,
        provider: _FollowModuleProvider,
        android: AndroidFollowProvider,
        profile_persistence: _ProfilePersistence,
    ):
        self._provider = provider
        self._android = android
        self._profile_persistence = profile_persistence

    def execute(self, context, module, budget) -> ModuleExecutionResult:
        context.logger.info("Executing FollowModule")
        prepared = module.execute(context, budget)
        domain = prepared.module_result
        if (
            domain is None
            or domain.status is not FollowModuleResultStatus.READY_TO_FOLLOW
        ):
            context.logger.info(
                "Follow candidate processing finished without execution",
                status=domain.status.value if domain is not None else "NO_RESULT",
                detail=prepared.detail or "",
            )
            return prepared
        if module.cancellation_requested():
            context.logger.info(
                "Follow cancellation acknowledged", next_stage="follow execution"
            )
            self._android.return_to_followers(context)
            return ModuleExecutionResult(
                execution_started=True,
                execution_finished=True,
                next_module_state=module.state,
                detail="Follow execution cancelled.",
                outcome=ModuleExecutionOutcome.SUCCESS,
            )
        context.logger.info(
            "Follow execution started", username=domain.candidate.username
        )
        android_result = self._android.execute_follow(context)
        context.logger.info(
            "AndroidFollowProvider completed", status=android_result.status
        )
        if android_result.status in (
            AndroidFollowStatus.SUCCESS,
            AndroidFollowStatus.REQUESTED,
        ):
            self._profile_persistence.mark_followed(
                domain.candidate.username,
                (
                    "following"
                    if android_result.status is AndroidFollowStatus.SUCCESS
                    else "requested"
                ),
            )
            if (
                domain.candidate.provider_type
                is CandidateProviderType.SPECIFIC_ACCOUNTS
            ):
                self._persist_specific_follow(
                    context,
                    domain.candidate,
                    status=android_result.status.value,
                    muted=android_result.muted,
                )
            else:
                self._persist_follow(
                    context, domain.candidate, muted=android_result.muted
                )
            outcome = module.complete_verified_follow()
        elif android_result.status is AndroidFollowStatus.GHOST_BLOCK_DETECTED:
            outcome = ModuleExecutionOutcome.ACTION_BLOCK
        else:
            outcome = ModuleExecutionOutcome.SUCCESS
        if domain.candidate.provider_type is CandidateProviderType.SPECIFIC_ACCOUNTS:
            module.mark_candidate_processed(context, domain.candidate)
        return ModuleExecutionResult(
            execution_started=True,
            execution_finished=True,
            next_module_state=module.state,
            detail=android_result.detail,
            outcome=outcome,
            module_result=android_result,
        )

    @staticmethod
    def _persist_follow(
        context: RuntimeContext, candidate: Candidate, *, muted: bool = False
    ) -> None:
        followed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            user = database.users.get_by_username(candidate.username)
            if user is None:
                user = database.users.create(candidate.username, followed_at, "FOLLOW")
            existing = database.follow.get(user.id)
            record = (
                replace(
                    existing,
                    username=candidate.username,
                    source=candidate.source,
                    follow_date=followed_at,
                    unfollowed=False,
                    unfollow_date=None,
                    last_session_id=str(context.session.session_id),
                    muted=muted,
                )
                if existing is not None
                else FollowRecord(
                    user_id=user.id,
                    username=candidate.username,
                    source=candidate.source,
                    follow_date=followed_at,
                    last_session_id=str(context.session.session_id),
                    muted=muted,
                )
            )
            database.follow.save(record)

    @staticmethod
    def _persist_specific_follow(
        context: RuntimeContext,
        candidate: Candidate,
        *,
        status: str,
        muted: bool = False,
    ) -> None:
        followed_at = utc_timestamp(datetime.now(timezone.utc))
        with RuntimeDatabase(context.session.account_directory) as database:
            database.specific_follow.upsert_username(
                candidate.username,
                {
                    "follow_date": followed_at,
                    "muted": int(muted),
                    "status": status,
                },
            )


class _SessionActivity:
    def __init__(self, stop_event: threading.Event) -> None:
        self._stop_event = stop_event

    def is_active(self, context: RuntimeContext) -> bool:
        return (
            not self._stop_event.is_set() and context.session_state.value == "Running"
        )


class NativeAccountRuntime:
    """Legacy-UI-shaped adapter around one fully composed native session."""

    def __init__(
        self,
        account: AssignedAccount,
        workspace: Path,
        *,
        controller: NativeSessionController | None = None,
    ) -> None:
        self.account = account
        self.workspace = workspace
        self.state = UiSessionState.IDLE
        self._stop_event = threading.Event()
        self._session_id = uuid4()
        self._controller = controller or self._compose()

    def start(self, state_changed) -> None:
        self.state = UiSessionState.STARTING
        state_changed(self.state)
        logger.info("Starting Native Runtime for %s", self.account.username)
        context = SessionContext(
            self._session_id,
            self.account.username,
            self.account.device_id,
            self.account.app_id,
            self.account.config_path.parent,
            datetime.now(timezone.utc),
        )
        try:
            result = self._controller.start(context)
            if result.startup_result.startup_failed:
                raise RuntimeError(
                    result.startup_result.failure_reason or "Native startup failed."
                )
            self.state = UiSessionState.STOPPED
            state_changed(self.state)
        except Exception:
            self.state = UiSessionState.ERROR
            state_changed(self.state)
            raise
        finally:
            writer = getattr(self, "_global_profile_writer", None)
            if writer is not None:
                writer.close()

    def request_stop(self, state_changed) -> None:
        self.state = UiSessionState.STOPPING
        state_changed(self.state)
        self._stop_event.set()

    def _compose(self) -> NativeSessionController:
        configuration = self._mapping(self.account.config_path)
        account_metadata = self._mapping(
            self.account.config_path.parent / "account.json"
        )
        filters = self._mapping(self.account.config_path.parent / "filters.yml")
        runtime_settings = dict(
            GlobalSettingsService(self.workspace).runtime_settings()
        )
        runtime_settings["wait_after_launching_instagram"] = (
            runtime_settings.get("wait_after_launching_instagram") or 0
        )
        runtime_settings.setdefault("follower_synchronization_limit", 200)
        runtime_logger = PythonRuntimeLogger()
        self._global_profile_writer = GlobalDatabaseWriter(self.workspace)
        persistence = _ProfilePersistence(self._global_profile_writer)
        extensions = account_metadata.get("runtime_extensions")
        follow_extensions = (
            extensions.get("follow") if isinstance(extensions, dict) else {}
        )
        if isinstance(follow_extensions, dict):
            runtime_settings["only_active_stories"] = bool(
                follow_extensions.get("only_active_stories")
            )
        android = AndroidFollowProvider(
            AndroidContactScraper(),
            profile_observer=persistence.observe,
            mute_after_follow=(
                bool(follow_extensions.get("mute_after_follow"))
                if isinstance(follow_extensions, dict)
                else False
            ),
        )
        modules = _FollowModuleProvider(
            configuration,
            filters,
            runtime_settings,
            android,
            persistence,
            self._stop_event.is_set,
        )
        executor = _NativeFollowExecutor(modules, android, persistence)
        scheduler = Scheduler(
            ModulePoolBuilder(),
            ModuleSelector(),
            BudgetCalculator(),
            ExecutionCoordinator(executor),
        )
        scheduler_loop = SchedulerLoop(
            scheduler,
            modules,
            _SessionActivity(self._stop_event),
            BackoffPolicy(),
            _RecoveryReporter(),
        )
        application_provider = AndroidApplicationProvider()
        instagram_launcher = InstagramLauncher(application_provider)
        startup = StartupPipeline.with_initial_stages(
            InternetChecker(AndroidNetworkProvider()),
            AirplaneModeController(AndroidAirplaneModeProvider()),
            instagram_launcher,
            AccountVerifier(AndroidInstagramProfileProvider(), _LoggingNotifier()),
            close_recent_apps=CloseRecentApps(AndroidRecentAppsProvider()),
            instagram_state_recovery=InstagramStateRecovery(
                AndroidInstagramStateProvider(),
                application_provider,
                instagram_launcher,
            ),
            follower_synchronization=FollowerSynchronization(
                AndroidFollowerReader(),
                RuntimeFollowerComparer(),
                RuntimeFollowerWriter(),
            ),
        )
        return NativeSessionController(
            startup,
            scheduler_loop,
            runtime_logger,
            runtime_settings=runtime_settings,
        )

    @staticmethod
    def _mapping(path: Path) -> dict[str, object]:
        if not path.is_file():
            return {}
        value = yaml.safe_load(path.read_bytes())
        return value if isinstance(value, dict) else {}


def create_native_runtime(account: AssignedAccount, workspace: Path):
    """Create the default account runtime without a legacy fallback."""

    return NativeAccountRuntime(account, workspace)
