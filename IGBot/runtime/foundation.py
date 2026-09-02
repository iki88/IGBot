"""Composition root for the independent runtime subsystem."""

from __future__ import annotations

from dataclasses import dataclass

from IGBot.runtime.compatibility import InstaAddictAdapter
from IGBot.runtime.hooks import HookManager
from IGBot.runtime.recovery import RecoveryController
from IGBot.runtime.scheduler import SchedulerEntryPoint
from IGBot.runtime.session import SessionLifecycle
from IGBot.runtime.shutdown import ShutdownController
from IGBot.runtime.startup import StartupPipeline


@dataclass(frozen=True, slots=True)
class RuntimeFoundation:
    """Runtime collaborators assembled without prescribing their implementations."""

    sessions: SessionLifecycle
    startup: StartupPipeline
    scheduler: SchedulerEntryPoint
    hooks: HookManager
    recovery: RecoveryController
    shutdown: ShutdownController
    compatibility: InstaAddictAdapter
