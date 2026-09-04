"""Eligible-module pool construction."""

from __future__ import annotations

from collections.abc import Iterable

from IGBot.runtime.modules import RuntimeModule


class ModulePoolBuilder:
    """Collect only modules that report themselves eligible."""

    def build(self, modules: Iterable[RuntimeModule]) -> tuple[RuntimeModule, ...]:
        return tuple(module for module in modules if module.is_eligible())
