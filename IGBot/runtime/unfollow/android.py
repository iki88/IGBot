"""UIAutomator2 execution for verified profile unfollowing."""

from __future__ import annotations

import time
from collections.abc import Callable

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.follow import AndroidFollowProvider, AndroidFollowStatus
from IGBot.runtime.ignore import log_ignored
from IGBot.runtime.navigation import NavigationResult, NavigationStatus
from IGBot.runtime.unfollow.models import AndroidUnfollowResult, AndroidUnfollowStatus


class AndroidUnfollowProvider:
    """Execute Unfollow UI actions while reusing exact Instagram Search."""

    _UNFOLLOW_ROW_IDS = ("follow_sheet_unfollow_row",)
    _DIALOG_IDS = ("dialog_container",)
    _CONFIRM_IDS = ("primary_button",)

    def __init__(
        self,
        search: AndroidFollowProvider,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        timeout: float = 3.0,
        poll_interval: float = 0.25,
    ) -> None:
        self._search = search
        self._clock = clock
        self._sleeper = sleeper
        self._timeout = timeout
        self._poll_interval = poll_interval

    def execute(self, context: RuntimeContext, username: str) -> AndroidUnfollowResult:
        result = self._execute(context, username)
        if context.cancellation_checkpoint("Unfollow navigation handoff"):
            return result
        context.logger.info(
            "[Unfollow] Restoring expected continuation screen.",
            expected="Instagram Search",
        )
        device = self._search._device(context)
        if (
            self._search._find_by_id(
                self._search._fresh_nodes(device), self._search._SEARCH_INPUT_IDS
            )
            is not None
        ):
            context.logger.info(
                "[Unfollow] Navigation handoff verified.",
                expected="Instagram Search",
            )
            return AndroidUnfollowResult(
                result.status,
                result.detail,
                result.username,
                NavigationResult(
                    NavigationStatus.SUCCESS, expected="Instagram Search"
                ),
            )
        for _attempt in range(2):
            restored = self._search.return_to_search(context)
            if restored.succeeded:
                context.logger.info(
                    "[Unfollow] Navigation handoff verified.",
                    expected="Instagram Search",
                )
                return AndroidUnfollowResult(
                    result.status,
                    result.detail,
                    result.username,
                    NavigationResult(
                        NavigationStatus.SUCCESS, expected="Instagram Search"
                    ),
                )
        context.logger.warning(
            "[Unfollow] Navigation handoff failed. Returning NAVIGATION_FAILED.",
            expected="Instagram Search",
        )
        return AndroidUnfollowResult(
            result.status,
            result.detail or "Instagram Search could not be restored.",
            result.username,
            NavigationResult(
                NavigationStatus.FAILED,
                "Instagram Search could not be restored.",
                expected="Instagram Search",
                actual="Unknown",
            ),
        )

    def _execute(self, context: RuntimeContext, username: str) -> AndroidUnfollowResult:
        if context.cancellation_checkpoint("Unfollow search"):
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.SEARCH_FAILED, "Unfollow cancelled.", username
            )
        context.logger.info("[Search] Searching account...", username=username)
        located = self._search.locate_source(context, username)
        if located.status is not AndroidFollowStatus.SUCCESS:
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.SEARCH_FAILED, located.detail, username
            )
        if context.cancellation_checkpoint("Unfollow profile opened"):
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.SEARCH_FAILED, "Unfollow cancelled.", username
            )
        context.logger.info("[Search] Account found.", username=username)
        device = self._search._device(context)
        nodes = self._search._fresh_nodes(device)
        detected = self._search._profile_username(nodes)
        if detected and context.ignore_service.is_ignored(detected):
            log_ignored(context, detected)
            restored = self._search.return_to_search(context)
            return AndroidUnfollowResult(
                (
                    AndroidUnfollowStatus.IGNORED
                    if restored.succeeded
                    else AndroidUnfollowStatus.NAVIGATION_FAILED
                ),
                None if restored.succeeded else restored.detail,
                username,
            )
        if detected.casefold() != username.casefold():
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.PROFILE_MISMATCH,
                f"Expected {username}, detected {detected or 'unknown'}.",
                username,
            )
        following = self._search._follow_button(nodes)
        if following is None or self._search._button_state(following) != "following":
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.NOT_FOLLOWING,
                "Profile does not show Following.",
                username,
            )
        context.logger.info("[Unfollow] Opening relationship menu.")
        unfollow = self._open_relationship_menu(context, device, following)
        if unfollow is None:
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.VERIFICATION_FAILED,
                "Relationship menu did not open.",
                username,
            )
        context.logger.info("[Unfollow] Unfollowing...")
        if context.cancellation_checkpoint("Unfollow action"):
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.VERIFICATION_FAILED,
                "Unfollow cancelled.",
                username,
            )
        self._search._tap(device, unfollow)
        context.logger.info("[Unfollow] Waiting for unfollow confirmation...")
        deadline = self._clock() + self._timeout
        confirmation_tapped = False
        while self._clock() < deadline:
            if context.cancellation_checkpoint("Unfollow verification"):
                return AndroidUnfollowResult(
                    AndroidUnfollowStatus.VERIFICATION_FAILED,
                    "Unfollow cancelled.",
                    username,
                )
            nodes = self._search._fresh_nodes(device)
            if not confirmation_tapped and self._search._find_by_id(
                nodes, self._DIALOG_IDS
            ):
                confirm = self._search._find_by_id(nodes, self._CONFIRM_IDS)
                if (
                    confirm is not None
                    and confirm.text.strip().casefold() == "unfollow"
                ):
                    context.logger.info("[Unfollow] Confirmation dialog detected.")
                    self._search._tap(device, confirm)
                    confirmation_tapped = True
                    continue
            button = self._search._follow_button(nodes)
            if button is not None and self._search._button_state(button) != "following":
                context.logger.info("[Unfollow] Unfollow confirmed.")
                return AndroidUnfollowResult(
                    AndroidUnfollowStatus.SUCCESS, username=username
                )
            self._sleeper(self._poll_interval)
        return AndroidUnfollowResult(
            AndroidUnfollowStatus.VERIFICATION_FAILED,
            "Following state did not clear before timeout.",
            username,
        )

    def _open_relationship_menu(
        self, context: RuntimeContext, device: object, following: object
    ):
        for attempt in range(2):
            if context.cancellation_checkpoint("Unfollow relationship menu"):
                return None
            self._search._tap(device, following)
            unfollow = self._wait_for_id(
                device, self._UNFOLLOW_ROW_IDS, context=context
            )
            if unfollow is not None:
                context.logger.info("[Unfollow] Relationship menu opened.")
                return unfollow
            if attempt == 0:
                context.logger.info(
                    "[Unfollow] Relationship menu not detected. Retrying..."
                )
        context.logger.warning(
            "[Unfollow] Relationship menu unavailable. Starting recovery."
        )
        return None

    def _wait_for_id(
        self, device: object, ids: tuple[str, ...], context: RuntimeContext | None = None
    ):
        deadline = self._clock() + self._timeout
        while self._clock() < deadline:
            if context is not None and context.cancellation_checkpoint(
                "Unfollow UI wait"
            ):
                return None
            node = self._search._find_by_id(self._search._fresh_nodes(device), ids)
            if node is not None:
                return node
            self._sleeper(self._poll_interval)
        return None
