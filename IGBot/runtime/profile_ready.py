"""Reusable Android profile-render readiness check.

Callers supply the resource IDs for their Instagram UI variant. This helper
does not parse profile facts or make module-specific qualification decisions.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable


def wait_for_profile_ready(
    device: object,
    initial_hierarchy: str,
    *,
    username_ids: tuple[str, ...],
    metric_ids: tuple[str, ...],
    timeout: float = 3.0,
    poll_interval: float = 0.25,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> str | None:
    """Return the first complete XML snapshot, or ``None`` on timeout.

    The initial snapshot is evaluated immediately; no sleep occurs for a
    profile whose username and all metric values are already present.
    """

    if timeout < 0 or poll_interval <= 0:
        raise ValueError("Profile readiness timing must be nonnegative and periodic")

    def has_value(root: ET.Element, identifiers: tuple[str, ...]) -> bool:
        return any(
            element.get("text", "").strip()
            and element.get("resource-id", "").rsplit("/", 1)[-1] in identifiers
            for element in root.iter("node")
        )

    deadline = clock() + timeout
    hierarchy = initial_hierarchy
    while True:
        root = ET.fromstring(hierarchy)
        if has_value(root, username_ids) and all(
            has_value(root, (identifier,)) for identifier in metric_ids
        ):
            return hierarchy
        remaining = deadline - clock()
        if remaining <= 0:
            return None
        sleeper(min(poll_interval, remaining))
        hierarchy = device.dump_hierarchy(compressed=False)
