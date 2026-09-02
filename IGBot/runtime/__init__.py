"""Independent IGBot runtime contracts.

This package defines the boundaries for the native IGBot runtime.  It is kept
separate from the legacy executable orchestration in :mod:`IGBot.core` so the
foundation can be introduced without changing current application behaviour.
"""

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.foundation import RuntimeFoundation
from IGBot.runtime.logging import RuntimeLogger
from IGBot.runtime.session import (
    SessionContext,
    SessionController,
    SessionHandle,
    SessionStartResult,
)
from IGBot.runtime.state import (
    AccountState,
    HookState,
    ModuleState,
    PhoneState,
    RuntimeState,
    SessionState,
)

__all__ = [
    "AccountState",
    "HookState",
    "ModuleState",
    "PhoneState",
    "RuntimeContext",
    "RuntimeFoundation",
    "RuntimeLogger",
    "RuntimeState",
    "SessionContext",
    "SessionController",
    "SessionHandle",
    "SessionStartResult",
    "SessionState",
]
