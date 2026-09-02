"""Session-scoped dependency shared by every native runtime component."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from IGBot.runtime.state import SessionState

if TYPE_CHECKING:
    from IGBot.runtime.logging import RuntimeLogger
    from IGBot.runtime.session.models import SessionContext
    from IGBot.runtime.startup.models import StartupResult


@dataclass(slots=True)
class RuntimeContext:
    """Own the shared references and evolving state for one running session.

    ``SessionContext`` remains the immutable admitted identity.  Runtime-specific
    references are added here as their subsystems are implemented, avoiding
    independent global state or long parameter lists.
    """

    session: SessionContext
    logger: RuntimeLogger
    runtime_settings: Mapping[str, object] = field(default_factory=dict)
    session_state: SessionState = SessionState.PENDING
    startup_result: StartupResult | None = None
