"""Session-scoped analytics facade."""

from __future__ import annotations

from pathlib import Path

from IGBot.runtime.analytics.database import AnalyticsDatabase, DailySummary
from IGBot.runtime.context import RuntimeContext


class AnalyticsService:
    """Apply live analytics updates without sharing Runtime Database state."""

    def __init__(self, account_directory: str | Path) -> None:
        self._account_directory = Path(account_directory)

    def update_profile_snapshot(
        self,
        username: str,
        *,
        posts: int | None,
        followers: int | None,
        following: int | None,
    ) -> DailySummary:
        with AnalyticsDatabase(self._account_directory) as database:
            return database.update_snapshot(
                username, posts=posts, followers=followers, following=following
            )

    def increment(self, username: str, counter: str, amount: int = 1) -> DailySummary:
        with AnalyticsDatabase(self._account_directory) as database:
            return database.increment(username, counter, amount)

    def history(self, days: int | None = 30) -> tuple[DailySummary, ...]:
        with AnalyticsDatabase(self._account_directory) as database:
            return database.history(days)


def increment_analytics(
    context: RuntimeContext, counter: str, amount: int = 1
) -> None:
    """Record verified work without allowing analytics to alter runtime outcomes."""

    if amount <= 0:
        return
    context.verified_interactions += amount
    if context.analytics is None:
        return
    try:
        context.analytics.increment(context.session.account_username, counter, amount)
    except Exception as error:  # noqa: BLE001 - analytics isolation boundary
        context.logger.warning(
            "Analytics interaction update failed", counter=counter, detail=str(error)
        )
