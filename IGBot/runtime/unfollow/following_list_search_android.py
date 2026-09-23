"""Android execution for runtime-history users searched in Following."""

from __future__ import annotations

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.unfollow.following_list_android import (
    AndroidFollowingListUnfollowProvider,
)
from IGBot.runtime.unfollow.models import AndroidUnfollowResult, AndroidUnfollowStatus


class AndroidFollowingListSearchUnfollowProvider(AndroidFollowingListUnfollowProvider):
    """Search the own Following list for one exact persisted username."""

    _WAIT_FOR_POPULATED_LIST = False
    _SEARCH_IDS = ("row_search_edit_text",)

    def execute(self, context: RuntimeContext, username: str) -> AndroidUnfollowResult:
        device = self._android._device(context)
        if not self._opened:
            context.logger.info("[Following List Search] Opening Following list...")
            opened = self._open_following_list(context, device)
            if opened is not None:
                return opened
            self._opened = True

        if not self._clear_search(context, device):
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.VERIFICATION_FAILED,
                "Following-list search field could not be reset.",
                username,
            )

        context.logger.info(
            "[Following List Search] Searching username...", username=username
        )
        search = self._wait_for_node(device, self._search_field)
        if search is None:
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.SEARCH_FAILED,
                "Following-list search field is unavailable.",
                username,
            )
        self._android._tap(device, search)
        device.send_keys(username, clear=True)
        self._sleeper(self._search_settle_delay())
        row = self._wait_for_exact_row(device, username)
        if row is None:
            self._clear_search(context, device)
            return AndroidUnfollowResult(
                AndroidUnfollowStatus.SEARCH_FAILED,
                "Username was not found in the Following list.",
                username,
            )

        context.logger.info(
            "[Following List Search] Username found.", username=username
        )
        result = self._unfollow_row(context, device, row)
        if not self._clear_search(context, device):
            context.logger.warning(
                "[Following List Search] Search field reset could not be verified."
            )
        return result

    def _clear_search(self, context: RuntimeContext, device: object) -> bool:
        search = self._wait_for_node(device, self._search_field)
        if search is None:
            return False
        if self._search_is_empty(search):
            return True
        self._android._tap(device, search)
        device.send_keys("", clear=True)
        cleared = self._wait_for_node(
            device,
            lambda nodes: next(
                (
                    node
                    for node in nodes
                    if self._android._id_has_suffix(node.resource_id, self._SEARCH_IDS)
                    and self._search_is_empty(node)
                ),
                None,
            ),
        )
        return cleared is not None

    def _search_field(self, nodes):
        return self._android._find_by_id(nodes, self._SEARCH_IDS)

    def _wait_for_exact_row(self, device: object, username: str):
        expected = username.casefold()
        deadline = self._clock() + self._timeout
        while self._clock() < deadline:
            hierarchy = device.dump_hierarchy(compressed=False)
            row = next(
                (
                    candidate
                    for candidate in self._rows(hierarchy)
                    if candidate.username.casefold() == expected
                ),
                None,
            )
            if row is not None:
                return row
            self._sleeper(self._poll_interval)
        return None

    @staticmethod
    def _search_is_empty(search: object) -> bool:
        return str(getattr(search, "text", "")).strip().casefold() in {"", "search"}
