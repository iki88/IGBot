"""Android implementation of the runtime network-provider boundary."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.network.models import NetworkCheckResult


class AndroidNetworkProvider:
    """Check Android Internet reachability through an isolated ADB probe."""

    def __init__(
        self,
        *,
        command_runner: Callable[
            ..., subprocess.CompletedProcess[str]
        ] = subprocess.run,
        adb_executable: str | Path | None = None,
        probe_host: str = "1.1.1.1",
    ) -> None:
        self._command_runner = command_runner
        self._adb_executable = str(adb_executable or self._discover_adb())
        self._probe_host = probe_host

    def check(self, context: RuntimeContext) -> NetworkCheckResult:
        """Probe an external address from the session's Android phone."""
        command = [
            self._adb_executable,
            "-s",
            context.session.phone_id,
            "shell",
            "ping",
            "-c",
            "1",
            "-W",
            "5",
            self._probe_host,
        ]
        try:
            result = self._command_runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except FileNotFoundError:
            return NetworkCheckResult(False, "ADB was not found.")
        except subprocess.TimeoutExpired:
            return NetworkCheckResult(False, "The Android network probe timed out.")
        except OSError as error:
            return NetworkCheckResult(
                False, f"The Android network probe failed: {error}"
            )

        if result.returncode == 0:
            return NetworkCheckResult(True)
        detail = (result.stderr or result.stdout or "Internet probe failed.").strip()
        return NetworkCheckResult(False, detail)

    @staticmethod
    def _discover_adb() -> str | Path:
        roots = [Path(__file__).resolve().parents[3]]
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
