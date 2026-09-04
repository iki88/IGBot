"""Shared contracts and state for native interaction modules."""

from IGBot.runtime.modules.contracts import RuntimeModule
from IGBot.runtime.modules.state_machine import (
    InteractionModule,
    InvalidModuleTransition,
    ModuleStateMachine,
)

__all__ = [
    "InteractionModule",
    "InvalidModuleTransition",
    "ModuleStateMachine",
    "RuntimeModule",
]
