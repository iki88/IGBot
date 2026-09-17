"""Open snapshot directories without duplicating Windows Explorer windows."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path


class SnapshotFolderOpener:
    """Use the Windows Shell inventory before opening a snapshot directory."""

    _SCRIPT = r"""
$target = [System.IO.Path]::GetFullPath($env:IGBOT_SNAPSHOT_DIRECTORY).TrimEnd('\')
$shell = New-Object -ComObject Shell.Application
$alreadyOpen = $false
foreach ($window in @($shell.Windows())) {
    try {
        if ([System.IO.Path]::GetFileName($window.FullName) -ine 'explorer.exe') {
            continue
        }
        $openPath = $window.Document.Folder.Self.Path
        if ($openPath -and ([System.IO.Path]::GetFullPath($openPath).TrimEnd('\') -ieq $target)) {
            $alreadyOpen = $true
            break
        }
    } catch {}
}
if ($alreadyOpen) { exit 10 }
Start-Process explorer.exe -ArgumentList @($target)
exit 0
"""

    def __init__(
        self,
        *,
        command_runner: Callable[
            ..., subprocess.CompletedProcess[str]
        ] = subprocess.run,
    ) -> None:
        self._command_runner = command_runner

    def open_if_needed(self, directory: Path) -> bool:
        """Return true when a new Explorer window was opened."""
        resolved = str(Path(directory).resolve())
        environment = os.environ.copy()
        environment["IGBOT_SNAPSHOT_DIRECTORY"] = resolved
        result = self._command_runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                self._SCRIPT,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=environment,
        )
        if result.returncode == 10:
            return False
        if result.returncode != 0:
            detail = (
                result.stderr or result.stdout or "Explorer command failed."
            ).strip()
            raise RuntimeError(detail)
        return True
