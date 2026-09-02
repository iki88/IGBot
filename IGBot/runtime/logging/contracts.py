"""Unified logging interface used by native runtime components."""

from __future__ import annotations

from typing import Protocol


class RuntimeLogger(Protocol):
    """Emit structured runtime messages without selecting a destination."""

    def debug(self, message: str, **fields: object) -> None:
        """Emit diagnostic detail."""
        ...

    def info(self, message: str, **fields: object) -> None:
        """Emit a normal lifecycle or operation message."""
        ...

    def warning(self, message: str, **fields: object) -> None:
        """Emit a recoverable or attention-worthy condition."""
        ...

    def error(self, message: str, **fields: object) -> None:
        """Emit a failed runtime operation or terminal condition."""
        ...
