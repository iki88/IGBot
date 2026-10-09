"""Verified Android execution for one Welcome DM."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import ClassVar

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.dm.models import AndroidDMResult, AndroidDMStatus
from IGBot.runtime.follow import AndroidFollowProvider, AndroidFollowStatus
from IGBot.runtime.navigation import NavigationResult, NavigationStatus


class AndroidDMProvider:
    """Search an exact profile and send one configured message."""

    _MESSAGE_BUTTON_IDS = ("button_container", "profile_header_message_button")
    _THREAD_IDS = (
        "direct_thread_header",
        "message_thread_container",
        "message_composer_bar",
    )
    _COMPOSER_IDS = ("row_thread_composer_edittext",)
    _SEND_IDS = (
        "row_thread_composer_send_button_container",
        "row_thread_composer_send_button_background",
    )
    _PRIVATE_OPTIONS_SHEET_IDS = ("bottom_sheet_container", "action_sheet_container")
    _PRIVATE_IDS = ("row_profile_header_empty_profile_notice_title",)
    _EMPTY_COMPOSER_TEXT: ClassVar[frozenset[str]] = frozenset(
        {"", "message…", "message...", "message"}
    )

    def __init__(
        self,
        search: AndroidFollowProvider,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = 0.25,
        timeout: float = 5.0,
    ) -> None:
        self._search = search
        self._sleeper = sleeper
        self._clock = clock
        self._poll_interval = poll_interval
        self._timeout = timeout

    def execute(
        self,
        context: RuntimeContext,
        username: str,
        message: str,
        *,
        private_fallback: bool = False,
        bounded_search: bool = False,
    ) -> AndroidDMResult:
        result = self._execute(
            context,
            username,
            message,
            private_fallback=private_fallback,
            bounded_search=bounded_search,
        )
        if context.cancellation_checkpoint("DM navigation recovery"):
            return result
        context.logger.info(
            "[DM] Restoring expected continuation screen.",
            expected="Instagram Search",
        )
        if self._restore_search(context):
            context.logger.info(
                "[DM] Navigation handoff verified.", expected="Instagram Search"
            )
            return AndroidDMResult(
                result.status,
                result.detail,
                NavigationResult(
                    NavigationStatus.SUCCESS, expected="Instagram Search"
                ),
            )
        context.logger.warning(
            "[DM] Navigation handoff failed. Returning NAVIGATION_FAILED.",
            expected="Instagram Search",
        )
        return AndroidDMResult(
            result.status,
            result.detail or "Instagram Search could not be restored.",
            NavigationResult(
                NavigationStatus.FAILED,
                "Instagram Search could not be restored.",
                expected="Instagram Search",
                actual="Unknown",
            ),
        )

    def _restore_search(self, context: RuntimeContext) -> bool:
        """Boundedly unwind a thread/profile back to Instagram Search."""

        device = self._search._device(context)
        if (
            self._search._find_by_id(
                self._nodes(device), self._search._SEARCH_INPUT_IDS
            )
            is not None
        ):
            return True
        for _attempt in range(2):
            restored = self._search.return_to_search(context)
            if restored.succeeded:
                return True
        return False

    def _execute(
        self,
        context: RuntimeContext,
        username: str,
        message: str,
        *,
        private_fallback: bool,
        bounded_search: bool,
    ) -> AndroidDMResult:
        context.logger.info("[DM] Searching...", username=username)
        if context.cancellation_checkpoint("DM search"):
            return AndroidDMResult(AndroidDMStatus.SEARCH_FAILED, "DM cancelled.")
        located = self._search.locate_source(
            context, username, bounded_accounts_scroll=bounded_search
        )
        if located.status is not AndroidFollowStatus.SUCCESS:
            if located.status is AndroidFollowStatus.SOURCE_NOT_FOUND:
                status = AndroidDMStatus.PROFILE_NOT_FOUND
            elif located.navigation_failed:
                status = AndroidDMStatus.SEARCH_FAILED
            else:
                status = AndroidDMStatus.PROFILE_UNAVAILABLE
            return AndroidDMResult(status, located.detail)
        if context.cancellation_checkpoint("DM profile opened"):
            return AndroidDMResult(AndroidDMStatus.SEARCH_FAILED, "DM cancelled.")
        device = self._search._device(context)
        nodes = self._nodes(device)
        opened_username = self._search._profile_username(nodes)
        if opened_username.casefold() != username.casefold():
            context.logger.warning(
                "[DM] Wrong profile opened.",
                expected=username,
                actual=opened_username or "unavailable",
            )
            return AndroidDMResult(
                AndroidDMStatus.PROFILE_NOT_FOUND,
                f"Expected {username}, opened {opened_username or 'unknown'}.",
            )
        if context.ignore_service.is_ignored(opened_username):
            return AndroidDMResult(AndroidDMStatus.IGNORED, "Recipient is ignored.")
        context.logger.info("[DM] Profile verified", username=username)

        button = self._message_button(nodes)
        if button is None:
            if private_fallback and self._is_private(nodes):
                if not self._open_private_thread(context, device, nodes):
                    return AndroidDMResult(
                        AndroidDMStatus.MESSAGE_BUTTON_NOT_FOUND,
                        "Private-profile Send message action is unavailable.",
                    )
            else:
                return AndroidDMResult(
                    AndroidDMStatus.MESSAGE_BUTTON_NOT_FOUND,
                    "Profile Message button is unavailable.",
                )
        else:
            context.logger.info("[DM] Opening thread")
            self._search._tap(device, button)
            if not self._wait_for(device, self._thread_open, context):
                return AndroidDMResult(
                    AndroidDMStatus.THREAD_FAILED, "DM thread did not open."
                )

        context.logger.info("[DM] Typing message")
        if context.cancellation_checkpoint("DM message typing"):
            return AndroidDMResult(AndroidDMStatus.TYPE_FAILED, "DM cancelled.")
        nodes = self._nodes(device)
        composer = self._search._find_by_id(nodes, self._COMPOSER_IDS)
        if composer is None:
            return AndroidDMResult(
                AndroidDMStatus.TYPE_FAILED, "DM composer is unavailable."
            )
        self._search._tap(device, composer)
        device.send_keys(message, clear=True)
        if not self._wait_for(
            device, lambda current: self._typed(current, message), context
        ):
            return AndroidDMResult(
                AndroidDMStatus.TYPE_FAILED,
                "DM composer did not contain the expected message.",
            )

        context.logger.info("[DM] Sending")
        for attempt in range(2):
            if context.cancellation_checkpoint("DM send"):
                return AndroidDMResult(AndroidDMStatus.SEND_FAILED, "DM cancelled.")
            nodes = self._nodes(device)
            send = self._search._find_by_id(nodes, self._SEND_IDS)
            if send is None:
                return AndroidDMResult(
                    AndroidDMStatus.SEND_FAILED, "DM Send button is unavailable."
                )
            current_composer = self._search._find_by_id(nodes, self._COMPOSER_IDS)
            outgoing_before = self._message_occurrences(
                nodes, message, composer=current_composer
            )
            self._search._tap(device, send)
            if self._wait_for(
                device,
                lambda current, outgoing_before=outgoing_before: self._sent(
                    current, message, outgoing_before
                ),
                context,
            ):
                context.logger.info("[DM] DM sent successfully", username=username)
                return AndroidDMResult(AndroidDMStatus.SUCCESS)
            if attempt == 0:
                context.logger.warning("[DM] Send not verified. Retrying...")
        return AndroidDMResult(AndroidDMStatus.SEND_FAILED, "DM send was not verified.")

    def _open_private_thread(self, context, device, nodes) -> bool:
        options = next(
            (
                node
                for node in nodes
                if node.description.strip().casefold() == "options"
            ),
            None,
        )
        if options is None:
            return False
        context.logger.info("[DM] Opening private profile Options")
        self._search._tap(device, options)
        sheet_nodes = self._wait_nodes(
            device,
            lambda current: self._search._find_by_id(
                current, self._PRIVATE_OPTIONS_SHEET_IDS
            )
            is not None,
            context,
        )
        if sheet_nodes is None:
            return False
        send_message = next(
            (
                node
                for node in sheet_nodes
                if self._search._id_has_suffix(
                    node.resource_id, ("action_sheet_row_text_view",)
                )
                and node.text.strip().casefold() == "send message"
            ),
            None,
        )
        if send_message is None:
            return False
        self._search._tap(device, send_message)
        return self._wait_for(device, self._thread_open, context)

    def _wait_for(self, device, predicate, context=None) -> bool:
        return self._wait_nodes(device, predicate, context) is not None

    def _wait_nodes(self, device, predicate, context=None):
        deadline = self._clock() + self._timeout
        while True:
            if context is not None and context.cancellation_checkpoint("DM UI wait"):
                return None
            nodes = self._nodes(device)
            if predicate(nodes):
                return nodes
            if self._clock() >= deadline:
                return None
            self._sleeper(self._poll_interval)

    def _nodes(self, device):
        return self._search._nodes(device.dump_hierarchy(compressed=False))

    def _thread_open(self, nodes) -> bool:
        return (
            all(
                self._search._find_by_id(nodes, (identifier,)) is not None
                for identifier in self._THREAD_IDS
            )
            and self._search._find_by_id(nodes, self._COMPOSER_IDS) is not None
        )

    def _message_button(self, nodes):
        return next(
            (
                node
                for node in nodes
                if self._search._id_has_suffix(
                    node.resource_id, self._MESSAGE_BUTTON_IDS
                )
                and (node.text or node.description).strip().casefold() == "message"
            ),
            None,
        )

    def _is_private(self, nodes) -> bool:
        return self._search._find_by_id(nodes, self._PRIVATE_IDS) is not None

    def _typed(self, nodes, message: str) -> bool:
        composer = self._search._find_by_id(nodes, self._COMPOSER_IDS)
        return composer is not None and composer.text == message

    def _sent(self, nodes, message: str, outgoing_before: int) -> bool:
        composer = self._search._find_by_id(nodes, self._COMPOSER_IDS)
        composer_empty = (
            composer is not None
            and composer.text.strip().casefold() in self._EMPTY_COMPOSER_TEXT
        )
        outgoing_added = (
            self._message_occurrences(nodes, message, composer=composer)
            > outgoing_before
        )
        return composer_empty or outgoing_added

    @staticmethod
    def _message_occurrences(nodes, message: str, *, composer) -> int:
        return sum(node.text == message for node in nodes if node is not composer)
