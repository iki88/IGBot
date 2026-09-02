"""Session Startup stage for the optional Airplane Mode cycle."""

from __future__ import annotations

from IGBot.runtime.airplane_mode import AirplaneModeProvider
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class AirplaneModeController:
    """Coordinate one provider-owned Airplane Mode cycle when configured."""

    SETTING_KEY = "toggle_airplane_mode_between_sessions"

    def __init__(self, provider: AirplaneModeProvider) -> None:
        self._provider = provider

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        """Return skipped, successful, or failed without waiting for Internet."""
        if context.runtime_settings.get(self.SETTING_KEY) is not True:
            context.logger.debug("Airplane Mode toggle is disabled")
            return StartupStageResult(
                StartupStageName.AIRPLANE_MODE,
                StartupStageStatus.SKIPPED,
            )

        context.logger.info("Toggling Airplane Mode between sessions")
        try:
            result = self._provider.toggle(context)
        except Exception as error:  # noqa: BLE001 - provider isolation boundary
            detail = f"Airplane Mode provider failed: {error}"
            context.logger.error(detail)
            return StartupStageResult(
                StartupStageName.AIRPLANE_MODE,
                StartupStageStatus.FAILED,
                detail=detail,
            )

        if not result.succeeded:
            detail = result.detail or "Airplane Mode toggle failed."
            context.logger.error(detail)
            return StartupStageResult(
                StartupStageName.AIRPLANE_MODE,
                StartupStageStatus.FAILED,
                detail=detail,
            )

        context.logger.info("Airplane Mode toggle complete")
        return StartupStageResult(
            StartupStageName.AIRPLANE_MODE,
            StartupStageStatus.SUCCESS,
        )
