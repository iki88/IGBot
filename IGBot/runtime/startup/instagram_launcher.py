"""Session Startup stage that launches and verifies Instagram."""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable

from IGBot.runtime.application import ApplicationProvider
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class InstagramLauncher:
    """Launch the configured Instagram package and verify foreground state."""

    WAIT_SETTING_KEY = "wait_after_launching_instagram"
    _PACKAGE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._]*")
    _DELAY_PATTERN = re.compile(r"(\d+)(?:-(\d+))?")

    def __init__(
        self,
        provider: ApplicationProvider,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        range_selector: Callable[[int, int], int] = random.randint,
    ) -> None:
        self._provider = provider
        self._sleeper = sleeper
        self._range_selector = range_selector

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        """Launch, wait, and verify the exact configured foreground package."""
        package = context.session.application_id.strip()
        if not package or self._PACKAGE_PATTERN.fullmatch(package) is None:
            return self._failed(
                context, "A valid Instagram Application ID is required."
            )

        try:
            delay = self._resolve_delay(
                context.runtime_settings.get(self.WAIT_SETTING_KEY, 0)
            )
        except (TypeError, ValueError) as error:
            return self._failed(context, str(error))

        context.logger.info("Launching Instagram", application_id=package)
        try:
            launch_result = self._provider.launch(context, package)
        except Exception as error:  # noqa: BLE001 - provider isolation boundary
            return self._failed(context, f"Instagram launch provider failed: {error}")

        if not launch_result.succeeded:
            return self._failed(
                context,
                launch_result.detail or "Instagram failed to launch.",
            )

        if delay:
            context.logger.info("Waiting after launching Instagram", seconds=delay)
            self._sleeper(delay)

        try:
            foreground = self._provider.foreground(context)
        except Exception as error:  # noqa: BLE001 - provider isolation boundary
            return self._failed(
                context, f"Foreground application provider failed: {error}"
            )

        if foreground.package != package:
            detail = foreground.detail
            if detail is None and foreground.package:
                detail = (
                    f"Instagram foreground verification failed: expected {package}, "
                    f"observed {foreground.package}."
                )
            return self._failed(
                context,
                detail or "Instagram foreground verification failed.",
            )

        context.logger.info("Instagram is in the foreground", application_id=package)
        return StartupStageResult(
            StartupStageName.INSTAGRAM_LAUNCH,
            StartupStageStatus.SUCCESS,
        )

    def _resolve_delay(self, configured: object) -> int:
        if isinstance(configured, bool):
            raise TypeError("Wait After Launching Instagram must be a number or range.")
        value = str(configured).strip()
        match = self._DELAY_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError(
                "Wait After Launching Instagram must use a value such as 10 or 8-12."
            )
        minimum = int(match.group(1))
        maximum = int(match.group(2) or minimum)
        if minimum > maximum:
            raise ValueError(
                "Wait After Launching Instagram range minimum cannot exceed maximum."
            )
        if match.group(2) is None:
            return minimum
        return self._range_selector(minimum, maximum)

    @staticmethod
    def _failed(context: RuntimeContext, detail: str) -> StartupStageResult:
        context.logger.error(detail)
        return StartupStageResult(
            StartupStageName.INSTAGRAM_LAUNCH,
            StartupStageStatus.FAILED,
            detail=detail,
        )
