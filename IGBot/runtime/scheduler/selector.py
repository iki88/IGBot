"""Unweighted random module selection."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence

from IGBot.runtime.modules import RuntimeModule


class ModuleSelector:
    """Select one module uniformly from an already eligible pool."""

    def __init__(
        self,
        chooser: Callable[[Sequence[RuntimeModule]], RuntimeModule] = random.choice,
    ) -> None:
        self._chooser = chooser

    def select(self, eligible: Sequence[RuntimeModule]) -> RuntimeModule | None:
        if not eligible:
            return None
        return self._chooser(eligible)
