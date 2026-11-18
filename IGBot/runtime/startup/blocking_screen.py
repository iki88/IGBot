"""Startup stage that stops before recovery can manipulate a blocking screen."""

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.startup.models import (
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)


class BlockingScreenCheck:
    def execute(self, context: RuntimeContext) -> StartupStageResult:
        blocked = context.blocking_screen_checkpoint("Post-launch startup")
        return StartupStageResult(
            StartupStageName.BLOCKING_SCREEN_CHECK,
            StartupStageStatus.FAILED if blocked else StartupStageStatus.SUCCESS,
            detail=(
                "Instagram requires operator action."
                if blocked
                else None
            ),
        )
