"""Recover Instagram to a deterministic profile surface before verification."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.application import ApplicationProvider
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.startup.contracts import StartupStage
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class InstagramStateProvider(Protocol):
    """Navigate arbitrary Instagram UI state to the account Profile surface."""

    def recover(self, context: RuntimeContext) -> bool:
        """Return whether a known Profile surface was reached."""
        ...


class InstagramStateRecovery:
    """Recover UI state, restarting Instagram only after bounded navigation fails."""

    def __init__(
        self,
        state_provider: InstagramStateProvider,
        application_provider: ApplicationProvider,
        relauncher: StartupStage,
    ) -> None:
        self._state_provider = state_provider
        self._application_provider = application_provider
        self._relauncher = relauncher

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        package = context.session.application_id.strip()
        context.logger.info("Recovering Instagram startup state")
        try:
            if self._state_provider.recover(context):
                context.logger.info("Instagram startup state recovered")
                return self._success()

            context.logger.warning(
                "Instagram startup state recovery exhausted; restarting application"
            )
            stopped = self._application_provider.force_stop(context, package)
            if not stopped.succeeded:
                return self._failed(
                    context, stopped.detail or "Instagram could not be force-stopped."
                )
            launched = self._relauncher.execute(context)
            if launched.status is StartupStageStatus.FAILED:
                return self._failed(
                    context, launched.detail or "Instagram could not be relaunched."
                )
            if not self._state_provider.recover(context):
                return self._failed(
                    context,
                    "Instagram did not reach a known Profile state after restart.",
                )
        except Exception as error:  # noqa: BLE001 - startup provider boundary
            return self._failed(context, f"Instagram state recovery failed: {error}")

        context.logger.info("Instagram startup state recovered after restart")
        return self._success()

    @staticmethod
    def _success() -> StartupStageResult:
        return StartupStageResult(
            StartupStageName.INSTAGRAM_STATE_RECOVERY,
            StartupStageStatus.SUCCESS,
        )

    @staticmethod
    def _failed(context: RuntimeContext, detail: str) -> StartupStageResult:
        context.logger.error(detail)
        return StartupStageResult(
            StartupStageName.INSTAGRAM_STATE_RECOVERY,
            StartupStageStatus.FAILED,
            detail=detail,
        )
