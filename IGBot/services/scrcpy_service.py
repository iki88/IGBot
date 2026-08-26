import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScrcpyLaunchResult:
    serial: str
    launched: bool
    reused: bool


class ScrcpyService:
    """Launches and tracks one scrcpy process for each managed Android device."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def launch(self, serial: str) -> ScrcpyLaunchResult:
        serial = serial.strip()
        if not serial:
            raise ValueError("Select exactly one managed phone before viewing it.")

        self.cleanup()
        with self._lock:
            existing = self._processes.get(serial)
            if existing is not None and existing.poll() is None:
                self._bring_to_foreground(existing.pid)
                return ScrcpyLaunchResult(serial, launched=False, reused=True)

        self._validate_device(serial)
        executable = self._find_executable()
        command = [
            str(executable),
            "-s",
            serial,
            "--window-title",
            f"IGBot - {serial}",
            "--no-audio",
        ]
        try:
            process = subprocess.Popen(command, cwd=executable.parent)
        except FileNotFoundError as error:
            raise RuntimeError(
                "scrcpy is unavailable or could not be started."
            ) from error
        except OSError as error:
            raise RuntimeError(f"scrcpy could not be started: {error}") from error

        with self._lock:
            duplicate = self._processes.get(serial)
            if duplicate is not None and duplicate.poll() is None:
                process.terminate()
                self._bring_to_foreground(duplicate.pid)
                return ScrcpyLaunchResult(serial, launched=False, reused=True)
            self._processes[serial] = process
        return ScrcpyLaunchResult(serial, launched=True, reused=False)

    def cleanup(self) -> tuple[str, ...]:
        removed = []
        with self._lock:
            for serial, process in tuple(self._processes.items()):
                if process.poll() is not None:
                    del self._processes[serial]
                    removed.append(serial)
        return tuple(removed)

    def has_session(self, serial: str) -> bool:
        self.cleanup()
        with self._lock:
            process = self._processes.get(serial)
            return process is not None and process.poll() is None

    @staticmethod
    def _validate_device(serial: str) -> None:
        try:
            result = subprocess.run(
                ["adb", "-s", serial, "get-state"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except FileNotFoundError as error:
            raise RuntimeError("ADB was not found.") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Device {serial} did not respond to ADB.") from error
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or str(error)).strip()
            if "unauthorized" in details.casefold():
                raise RuntimeError(
                    f"Device {serial} is unauthorized. Accept the USB debugging prompt."
                ) from error
            raise RuntimeError(
                f"Device {serial} is offline or disconnected."
            ) from error

        state = result.stdout.strip().casefold()
        if state == "unauthorized":
            raise RuntimeError(
                f"Device {serial} is unauthorized. Accept the USB debugging prompt."
            )
        if state != "device":
            raise RuntimeError(f"Device {serial} is offline or disconnected.")

    def _find_executable(self) -> Path:
        for candidate in self._bundled_candidates():
            if candidate.is_file():
                return candidate.resolve()

        configured = os.environ.get("SCRCPY_PATH")
        if configured:
            configured_path = Path(configured).expanduser()
            if configured_path.is_dir():
                configured_path /= "scrcpy.exe"
            if configured_path.is_file():
                return configured_path.resolve()

        discovered = shutil.which("scrcpy")
        if discovered:
            return Path(discovered).resolve()
        raise RuntimeError(
            "scrcpy is unavailable. Bundle it in tools/scrcpy, set SCRCPY_PATH, "
            "or install it on the system PATH."
        )

    def _bundled_candidates(self) -> tuple[Path, ...]:
        roots = [self._workspace_root, Path(__file__).resolve().parents[2]]
        bundled_root = getattr(sys, "_MEIPASS", None)
        if bundled_root:
            roots.append(Path(bundled_root))
        if getattr(sys, "frozen", False):
            roots.append(Path(sys.executable).resolve().parent)

        unique_roots = tuple(dict.fromkeys(root.resolve() for root in roots))
        relative_locations = (
            Path("tools") / "scrcpy" / "scrcpy.exe",
            Path("resources") / "scrcpy" / "scrcpy.exe",
            Path("scrcpy") / "scrcpy.exe",
            Path("scrcpy.exe"),
        )
        return tuple(
            root / relative for root in unique_roots for relative in relative_locations
        )

    @staticmethod
    def _bring_to_foreground(process_id: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def callback(window, _parameter):
                window_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(window, ctypes.byref(window_pid))
                if window_pid.value == process_id and user32.IsWindowVisible(window):
                    found.append(window)
                    return False
                return True

            user32.EnumWindows(callback, 0)
            if not found:
                return False
            user32.ShowWindow(found[0], 9)
            return bool(user32.SetForegroundWindow(found[0]))
        except (AttributeError, OSError):
            return False
