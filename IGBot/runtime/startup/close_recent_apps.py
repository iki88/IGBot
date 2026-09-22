"""Session Startup stage for lock-aware Android recent-app cleanup."""

from __future__ import annotations

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.recent_apps import RecentAppsProvider
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class CloseRecentApps:
    """Close removable recent apps exactly once during Session Startup."""

    SETTING_KEY = "close_recent_apps_before_session"

    def __init__(self, provider: RecentAppsProvider) -> None:
        self._provider = provider

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        if context.runtime_settings.get(self.SETTING_KEY) is not True:
            return StartupStageResult(
                StartupStageName.CLOSE_RECENT_APPS,
                StartupStageStatus.SKIPPED,
            )

        try:
            result = self._provider.close(context)
        except Exception as error:  # noqa: BLE001 - provider isolation boundary
            detail = f"Close Recent Apps provider failed: {error}"
            context.logger.error(detail)
            return StartupStageResult(
                StartupStageName.CLOSE_RECENT_APPS,
                StartupStageStatus.FAILED,
                detail=detail,
            )
        if not result.succeeded:
            detail = result.detail or "Closing recent apps failed."
            context.logger.error(detail)
            return StartupStageResult(
                StartupStageName.CLOSE_RECENT_APPS,
                StartupStageStatus.FAILED,
                detail=detail,
            )
        if result.closed_count:
            context.logger.info(f"Closed {result.closed_count} recent apps.")
        else:
            context.logger.info("No removable recent apps found.")
        return StartupStageResult(
            StartupStageName.CLOSE_RECENT_APPS,
            StartupStageStatus.SUCCESS,
        )
