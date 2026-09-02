"""Shared Android command-line discovery for runtime providers."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def discover_adb() -> str | Path:
    """Return bundled ADB when available, otherwise defer to the system PATH."""
    roots = [Path(__file__).resolve().parents[2]]
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        roots.append(Path(bundled_root))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)

    for root in roots:
        candidate = root / "tools" / "scrcpy" / "adb.exe"
        if candidate.is_file():
            return candidate.resolve()
    return shutil.which("adb") or "adb"
