from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AssignedAccount:
    username: str
    device_id: str
    app_id: str
    config_path: Path


@dataclass(frozen=True)
class DeviceRecord:
    serial: str
    phone_name: str
    connected: bool
    accounts: tuple[AssignedAccount, ...] = ()

    @property
    def status(self) -> str:
        return "" if self.connected else "Offline"


@dataclass(frozen=True)
class DeviceFleetSnapshot:
    devices: tuple[DeviceRecord, ...]
    error: str | None = None
