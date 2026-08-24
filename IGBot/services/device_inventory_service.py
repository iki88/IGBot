import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from IGBot.core.device import DeviceFleetSnapshot, DeviceRecord
from IGBot.core.phone_manager import PhoneManager
from IGBot.services.account_assignment_service import AccountAssignmentService


class DeviceInventoryService:
    """Maintains the ordered IGBot device inventory around ADB discovery."""

    def __init__(
        self,
        inventory_path: Path,
        account_assignments: AccountAssignmentService,
    ) -> None:
        self._inventory_path = inventory_path
        self._account_assignments = account_assignments

    @classmethod
    def for_workspace(cls, workspace_root: Path) -> "DeviceInventoryService":
        local_app_data = os.environ.get("LOCALAPPDATA")
        data_directory = (
            Path(local_app_data) / "IGBot" if local_app_data else Path.home() / ".igbot"
        )
        return cls(
            inventory_path=data_directory / "devices.json",
            account_assignments=AccountAssignmentService(workspace_root / "accounts"),
        )

    def refresh(self) -> DeviceFleetSnapshot:
        discovery = PhoneManager.discover_devices()
        if discovery.error:
            return DeviceFleetSnapshot(
                devices=self._records_from_state(self._load_state(), set()),
                error=discovery.error,
            )

        connected = set(discovery.devices)
        state = self._load_state()
        suppressed = {serial for serial in state["suppressed"] if serial in connected}
        known_serials = [
            entry["serial"]
            for entry in state["devices"]
            if entry["serial"] not in suppressed
        ]

        for serial in discovery.devices:
            if serial not in known_serials and serial not in suppressed:
                state["devices"].append({"serial": serial, "phone_name": ""})
                known_serials.append(serial)

        state["suppressed"] = sorted(suppressed)
        self._save_state(state)
        return DeviceFleetSnapshot(devices=self._records_from_state(state, connected))

    def delete(self, serial: str, connected: bool) -> None:
        state = self._load_state()
        state["devices"] = [
            entry for entry in state["devices"] if entry["serial"] != serial
        ]
        if connected:
            state["suppressed"] = sorted(set(state["suppressed"]) | {serial})
        else:
            state["suppressed"] = [
                value for value in state["suppressed"] if value != serial
            ]
        self._save_state(state)

    def _records_from_state(
        self, state: dict[str, list], connected: set[str]
    ) -> tuple[DeviceRecord, ...]:
        accounts_by_device = self._account_assignments.load_by_device()
        return tuple(
            DeviceRecord(
                serial=entry["serial"],
                phone_name=entry.get("phone_name", ""),
                connected=entry["serial"] in connected,
                accounts=accounts_by_device.get(entry["serial"], ()),
            )
            for entry in state["devices"]
        )

    def _load_state(self) -> dict[str, list]:
        try:
            raw = json.loads(self._inventory_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"devices": [], "suppressed": []}
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Could not read device inventory {self._inventory_path}: {error}"
            ) from error

        devices = raw.get("devices", [])
        suppressed = raw.get("suppressed", [])
        if not isinstance(devices, list) or not isinstance(suppressed, list):
            raise TypeError(
                f"Device inventory {self._inventory_path} has an invalid format"
            )
        if any(
            not isinstance(entry, dict)
            or not isinstance(entry.get("serial"), str)
            or not isinstance(entry.get("phone_name", ""), str)
            for entry in devices
        ) or any(not isinstance(serial, str) for serial in suppressed):
            raise TypeError(
                f"Device inventory {self._inventory_path} has invalid device records"
            )
        return {"devices": devices, "suppressed": suppressed}

    def _save_state(self, state: dict[str, list]) -> None:
        self._inventory_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._inventory_path.parent,
            delete=False,
        ) as temporary_file:
            json.dump(state, temporary_file, indent=2)
            temporary_path = Path(temporary_file.name)
        try:
            os.replace(temporary_path, self._inventory_path)
        finally:
            temporary_path.unlink(missing_ok=True)
