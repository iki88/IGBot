"""Unified, behavior-free interaction-module state machine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from enum import StrEnum

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.state import ModuleState, StateTransition


class InteractionModule(StrEnum):
    """Interaction modules governed by the shared state machine."""

    FOLLOW = "Follow"
    LIKE = "Like"
    COMMENT = "Comment"
    STORY = "Story"
    DM = "DM"


class InvalidModuleTransition(RuntimeError):
    """Raised when a caller requests an illegal module-state transition."""


class ModuleStateMachine:
    """Own lifecycle state and eligibility for one interaction module."""

    def __init__(
        self,
        context: RuntimeContext,
        module: InteractionModule,
        *,
        enabled: bool,
        configured: bool,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if enabled and not configured:
            raise ValueError("An enabled module must be configured")
        self._context = context
        self._module = module
        self._enabled = enabled
        self._configured = configured
        self._clock = clock
        self._state = ModuleState.READY if enabled else ModuleState.DISABLED
        self._backoff_until: datetime | None = None
        self._daily_limit_reached_on: date | None = None

    @property
    def context(self) -> RuntimeContext:
        return self._context

    @property
    def module(self) -> InteractionModule:
        return self._module

    @property
    def state(self) -> ModuleState:
        return self._state

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def backoff_until(self) -> datetime | None:
        return self._backoff_until

    def is_eligible(self) -> bool:
        """Refresh time-based state and return the complete eligibility decision."""

        self._refresh_time_based_state(self._now())
        return (
            self._state is ModuleState.READY
            and self._enabled
            and self._configured
            and self._daily_limit_reached_on is None
            and self._backoff_until is None
        )

    def start(self) -> StateTransition[ModuleState]:
        """Enter RUNNING after the same eligibility gate used by the scheduler."""

        if not self.is_eligible():
            raise InvalidModuleTransition(
                f"{self._module.value} cannot start from {self._state.value}"
            )
        return self._transition(ModuleState.RUNNING, self._now())

    def mark_ready(self) -> StateTransition[ModuleState]:
        """Return completed RUNNING work to READY."""

        if self._state is not ModuleState.RUNNING:
            raise InvalidModuleTransition("Only a running module can become ready")
        return self._transition(ModuleState.READY, self._now())

    def enter_backoff(self, backoff_until: datetime) -> StateTransition[ModuleState]:
        """Temporarily remove READY or RUNNING work from eligibility."""

        now = self._now()
        until = self._as_utc(backoff_until)
        if self._state not in (ModuleState.READY, ModuleState.RUNNING):
            raise InvalidModuleTransition(
                f"{self._module.value} cannot back off from {self._state.value}"
            )
        if until <= now:
            raise ValueError("backoff_until must be in the future")
        self._backoff_until = until
        return self._transition(ModuleState.BACKOFF, now)

    def mark_daily_limit_reached(self) -> StateTransition[ModuleState]:
        """Remove the module from eligibility until the next UTC day."""

        if self._state not in (
            ModuleState.READY,
            ModuleState.RUNNING,
            ModuleState.BACKOFF,
        ):
            raise InvalidModuleTransition(
                f"{self._module.value} cannot reach its limit from {self._state.value}"
            )
        now = self._now()
        self._backoff_until = None
        self._daily_limit_reached_on = now.date()
        return self._transition(ModuleState.DAILY_LIMIT_REACHED, now)

    def disable(self) -> StateTransition[ModuleState]:
        """Disable the module and clear temporary eligibility metadata."""

        now = self._now()
        self._enabled = False
        self._backoff_until = None
        self._daily_limit_reached_on = None
        return self._transition(ModuleState.DISABLED, now)

    def enable(self) -> StateTransition[ModuleState]:
        """Enable a configured module in READY state."""

        if not self._configured:
            raise InvalidModuleTransition("An unconfigured module cannot be enabled")
        if self._state is not ModuleState.DISABLED:
            raise InvalidModuleTransition("Only a disabled module can be enabled")
        now = self._now()
        self._enabled = True
        return self._transition(ModuleState.READY, now)

    def _refresh_time_based_state(self, now: datetime) -> None:
        if (
            self._state is ModuleState.BACKOFF
            and self._backoff_until is not None
            and now >= self._backoff_until
        ):
            self._backoff_until = None
            self._transition(ModuleState.READY, now)
        if (
            self._state is ModuleState.DAILY_LIMIT_REACHED
            and self._daily_limit_reached_on is not None
            and now.date() > self._daily_limit_reached_on
        ):
            self._daily_limit_reached_on = None
            self._transition(ModuleState.READY, now)

    def _transition(
        self, state: ModuleState, occurred_at: datetime
    ) -> StateTransition[ModuleState]:
        previous = self._state
        self._state = state
        return StateTransition(previous, state, occurred_at)

    def _now(self) -> datetime:
        return self._as_utc(self._clock())

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Module state timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)
