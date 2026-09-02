"""Executable Internet availability stage for Session Startup."""

from __future__ import annotations

import time
from collections.abc import Callable

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.network import NetworkProvider
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class InternetChecker:
    """Wait until the platform network provider reports Internet availability."""

    RETRY_SECONDS = 60
    RETRY_MESSAGE = "No Internet connection. Retrying in 60 seconds..."

    def __init__(
        self,
        provider: NetworkProvider,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider = provider
        self._sleeper = sleeper

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        """Poll until Internet is available, treating waiting as normal startup."""
        while True:
            try:
                observation = self._provider.check(context)
            except Exception as error:  # noqa: BLE001 - provider isolation boundary
                detail = f"Internet provider failed: {error}"
                context.logger.error(detail)
                return StartupStageResult(
                    StartupStageName.INTERNET,
                    StartupStageStatus.FAILED,
                    detail=detail,
                    internet_available=False,
                )

            if observation.available:
                return StartupStageResult(
                    StartupStageName.INTERNET,
                    StartupStageStatus.SUCCESS,
                    internet_available=True,
                )

            context.logger.warning(self.RETRY_MESSAGE)
            self._sleeper(self.RETRY_SECONDS)
