"""Rendering for native DM message templates."""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Sequence


_SPINTAX = re.compile(r"\{([^{}]*\|[^{}]*)\}")


class DMMessageRenderer:
    """Resolve non-nested spintax blocks once for a recipient."""

    def __init__(self, chooser: Callable[[Sequence[str]], str] = random.choice) -> None:
        self._chooser = chooser

    def render(self, template: str) -> str:
        return _SPINTAX.sub(
            lambda match: self._chooser(tuple(match.group(1).split("|"))), template
        )
