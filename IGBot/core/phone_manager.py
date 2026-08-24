import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceDiscoveryResult:
    devices: list[str]
    error: str | None = None


class PhoneManager:
    """Basic phone discovery and status checks."""

    @staticmethod
    def discover_devices() -> DeviceDiscoveryResult:
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                check=True,
            )

            devices = []
            for line in result.stdout.splitlines()[1:]:
                if "\tdevice" in line:
                    devices.append(line.split("\t")[0])

            return DeviceDiscoveryResult(devices=devices)
        except FileNotFoundError:
            return DeviceDiscoveryResult(
                devices=[],
                error="ADB was not found. Install Android platform-tools and add adb to PATH.",
            )
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or str(error)).strip()
            return DeviceDiscoveryResult(
                devices=[], error=f"ADB device discovery failed: {details}"
            )

    @staticmethod
    def get_connected_devices() -> list[str]:
        """Return serial numbers for Android devices currently ready for use."""
        return PhoneManager.discover_devices().devices

    @staticmethod
    def is_connected(device_id: str) -> bool:
        return device_id in PhoneManager.get_connected_devices()
