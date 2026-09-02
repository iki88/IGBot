"""Identity and context for one native account session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from IGBot.runtime.context import RuntimeContext
    from IGBot.runtime.startup.models import StartupResult


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Validated references required by every session stage.

    Credentials are intentionally excluded.  Implementations obtain sensitive
    account data through the established account services at execution time.
    """

    session_id: UUID
    account_username: str
    phone_id: str
    application_id: str
    account_directory: Path
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SessionHandle:
    """Stable handle returned when a session lifecycle is accepted."""

    session_id: UUID


@dataclass(frozen=True, slots=True)
class SessionStartResult:
    """Observable outcome of startup orchestration for one session."""

    handle: SessionHandle
    context: RuntimeContext
    startup_result: StartupResult
    scheduler_started: bool
