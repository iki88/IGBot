import subprocess
from typing import List


class PhoneManager:
    """Basic phone discovery and status checks."""

    @staticmethod
    def get_connected_devices() -> List[str]:
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

            return devices
        except Exception:
            return []

    @staticmethod
    def is_connected(device_id: str) -> bool:
        return device_id in PhoneManager.get_connected_devices()
