"""Single-method contract implemented by every startup stage."""

from __future__ import annotations

from typing import Protocol

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.startup.models import StartupStageResult


class StartupStage(Protocol):
    """A dependency-injected unit in the ordered startup pipeline."""

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        """Return the structured result of this stage."""
        ...
