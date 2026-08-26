import re
import subprocess


class AndroidPackageService:
    """Provides read-only installed-package inspection through ADB."""

    @staticmethod
    def installed_packages(serial: str) -> tuple[str, ...]:
        if not serial or serial == "ARCHIVED_ACCOUNTS":
            raise ValueError("A connected Android device is required.")
        try:
            result = subprocess.run(
                ["adb", "-s", serial, "shell", "pm", "list", "packages"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except FileNotFoundError as error:
            raise RuntimeError("ADB was not found.") from error
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            details = getattr(error, "stderr", "") or str(error)
            raise RuntimeError(
                f"Could not load installed applications: {details.strip()}"
            ) from error
        packages = sorted(
            {
                line.removeprefix("package:").strip()
                for line in result.stdout.splitlines()
                if line.startswith("package:") and line.removeprefix("package:").strip()
            }
        )
        if not packages:
            raise RuntimeError(
                "No installed application packages were reported by the device."
            )
        return tuple(packages)

    @staticmethod
    def foreground_package(serial: str) -> str:
        if not serial or serial == "ARCHIVED_ACCOUNTS":
            raise ValueError("A connected Android device is required.")
        commands = (
            ("dumpsys", "window", "windows"),
            ("dumpsys", "activity", "activities"),
        )
        failures = []
        for shell_command in commands:
            try:
                result = subprocess.run(
                    ["adb", "-s", serial, "shell", *shell_command],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
            except FileNotFoundError as error:
                raise RuntimeError("ADB was not found.") from error
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                details = getattr(error, "stderr", "") or str(error)
                failures.append(details.strip())
                continue
            package = AndroidPackageService._parse_foreground_package(result.stdout)
            if package:
                return package

        details = next((failure for failure in failures if failure), "")
        suffix = f": {details}" if details else "."
        raise RuntimeError(
            f"No foreground Android application could be detected{suffix}"
        )

    @staticmethod
    def _parse_foreground_package(output: str) -> str | None:
        match = re.search(
            r"(?:mCurrentFocus|mFocusedApp|mResumedActivity|topResumedActivity|"
            r"ResumedActivity)\s*[:=].*?\b([A-Za-z][A-Za-z0-9._]*)/",
            output,
        )
        return match.group(1) if match else None
