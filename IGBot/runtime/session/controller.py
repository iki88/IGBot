"""Executable orchestration for one native account session."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.logging import RuntimeLogger
from IGBot.runtime.scheduler.contracts import SchedulerEntryPoint
from IGBot.runtime.session.models import (
    SessionContext,
    SessionHandle,
    SessionStartResult,
)
from IGBot.runtime.startup.pipeline import StartupPipeline
from IGBot.runtime.state import SessionState


class SessionController:
    """Run Session Startup and hand completed startup to the scheduler."""

    def __init__(
        self,
        startup_pipeline: StartupPipeline,
        scheduler: SchedulerEntryPoint,
        logger: RuntimeLogger,
        *,
        runtime_settings: Mapping[str, object] | None = None,
    ) -> None:
        self._startup_pipeline = startup_pipeline
        self._scheduler = scheduler
        self._logger = logger
        self._runtime_settings = dict(runtime_settings or {})
        self._contexts: dict[UUID, RuntimeContext] = {}

    def start(self, context: SessionContext) -> SessionStartResult:
        """Execute startup once and enter scheduling only on success."""
        if context.session_id in self._contexts:
            raise RuntimeError("Startup has already executed for this session.")

        handle = SessionHandle(context.session_id)
        runtime_context = RuntimeContext(
            context, self._logger, runtime_settings=dict(self._runtime_settings)
        )
        runtime_context.session_state = SessionState.STARTING
        self._contexts[context.session_id] = runtime_context
        try:
            self._logger.info("Running StartupPipeline")
            startup_result = self._startup_pipeline.execute(runtime_context)
        except Exception:
            runtime_context.session_state = SessionState.FAILED
            raise
        runtime_context.startup_result = startup_result
        if startup_result.startup_failed:
            if runtime_context.session_state is not SessionState.WAITING_FOR_OPERATOR:
                runtime_context.session_state = SessionState.FAILED
            return SessionStartResult(handle, runtime_context, startup_result, False)

        runtime_context.session_state = SessionState.RUNNING
        try:
            self._logger.info("Running SchedulerLoop")
            self._scheduler.start(runtime_context)
        except Exception:
            runtime_context.session_state = SessionState.FAILED
            raise
        runtime_context.session_state = SessionState.COMPLETED
        return SessionStartResult(handle, runtime_context, startup_result, True)

    def state_for(self, session_id: UUID) -> SessionState:
        """Return the tracked state, defaulting to Pending before start."""
        context = self._contexts.get(session_id)
        return context.session_state if context else SessionState.PENDING

    def context_for(self, session_id: UUID) -> RuntimeContext | None:
        """Return the session-owned RuntimeContext when one has been created."""
        return self._contexts.get(session_id)

    def is_active(self, context: RuntimeContext) -> bool:
        """Report whether this controller still owns a running session."""

        owned = self._contexts.get(context.session.session_id)
        return owned is context and context.session_state is SessionState.RUNNING
