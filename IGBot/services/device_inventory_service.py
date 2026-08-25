import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from IGBot.core.device import DeviceFleetSnapshot, DeviceRecord
from IGBot.core.phone_manager import PhoneManager
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.archive_service import ARCHIVED_ACCOUNTS, ArchiveService
from IGBot.services.transfer_service import TransferService


class DeviceInventoryService:
    """Maintains the ordered IGBot device inventory around ADB discovery."""

    def __init__(
        self,
        inventory_path: Path,
        account_assignments: AccountAssignmentService,
        workspace_root: Path | None = None,
    ) -> None:
        self._inventory_path = inventory_path
        self._account_assignments = account_assignments
        self.transfer_service = TransferService(account_assignments)
        self.archive_service = ArchiveService(account_assignments)
        self._workspace_root = workspace_root or inventory_path.parent.parent

    @classmethod
    def for_workspace(cls, workspace_root: Path) -> "DeviceInventoryService":
        local_app_data = os.environ.get("LOCALAPPDATA")
        data_directory = (
            Path(local_app_data) / "IGBot" if local_app_data else Path.home() / ".igbot"
        )
        return cls(
            inventory_path=data_directory / "devices.json",
            account_assignments=AccountAssignmentService(workspace_root / "accounts"),
            workspace_root=workspace_root,
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
        state["deleted"] = sorted(set(state["deleted"]))
        self._save_state(state)
        return DeviceFleetSnapshot(devices=self._records_from_state(state, connected))

    def unmanaged_devices(self) -> tuple[str, ...]:
        discovery = PhoneManager.discover_devices()
        if discovery.error:
            raise RuntimeError(discovery.error)
        managed = {entry["serial"] for entry in self._load_state()["devices"]}
        return tuple(serial for serial in discovery.devices if serial not in managed)

    def add_device(self, serial: str, phone_name: str = "") -> None:
        serial = serial.strip()
        if not serial or serial not in self.unmanaged_devices():
            raise ValueError("Select a connected Android device that is not managed.")
        state = self._load_state()
        state["devices"].append({"serial": serial, "phone_name": phone_name.strip()})
        state["deleted"] = [item for item in state["deleted"] if item != serial]
        self._save_state(state)

    def add_account(self, username: str, password: str, serial: str):
        if serial not in {entry["serial"] for entry in self._load_state()["devices"]}:
            raise ValueError(
                "The selected phone is not in the managed device inventory."
            )
        return self._account_assignments.create_account(
            username,
            password,
            serial,
            self._workspace_root / "config-examples",
        )

    def account_configuration(self, account):
        return self._account_assignments.load_configuration(account.config_path)

    def update_account_configuration(self, account, username, password, app_id):
        return self._account_assignments.update_configuration(
            account, username, password, app_id
        )

    def rename_device(self, serial: str, phone_name: str) -> None:
        state = self._load_state()
        for entry in state["devices"]:
            if entry["serial"] == serial:
                entry["phone_name"] = phone_name.strip()
                self._save_state(state)
                return
        raise ValueError(f"Device {serial} is not in the inventory")

    def device_directory(self, serial: str) -> Path:
        if serial not in {entry["serial"] for entry in self._load_state()["devices"]}:
            raise ValueError(f"Device {serial} is not in the inventory")
        directory = self._workspace_root / "phones" / serial
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def archived_accounts(self):
        accounts = list(
            self._account_assignments.load_by_device().get(ARCHIVED_ACCOUNTS, ())
        )
        archived_directory = self._workspace_root / "archived"
        if not archived_directory.is_dir():
            return tuple(accounts)
        for config_path in sorted(archived_directory.glob("*/config.y*ml")):
            account = self._account_assignments._load_account(config_path)
            if account is not None:
                accounts.append(account)
        return tuple(accounts)

    def delete(self, serial: str) -> None:
        assigned_accounts = self._account_assignments.load_by_device().get(serial, ())
        if assigned_accounts:
            raise RuntimeError(
                "This device currently contains assigned accounts.\n\n"
                "Move or archive all accounts before deleting this device.\n\n"
                "Device deletion for populated devices will be enabled in Sprint 4B "
                "after account transfer and archival are implemented."
            )
        state = self._load_state()
        state["devices"] = [
            entry for entry in state["devices"] if entry["serial"] != serial
        ]
        state["deleted"] = sorted(set(state["deleted"]) | {serial})
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
            return {"devices": [], "deleted": []}
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Could not read device inventory {self._inventory_path}: {error}"
            ) from error

        devices = raw.get("devices", [])
        deleted = raw.get("deleted", raw.get("suppressed", []))
        if not isinstance(devices, list) or not isinstance(deleted, list):
            raise TypeError(
                f"Device inventory {self._inventory_path} has an invalid format"
            )
        if any(
            not isinstance(entry, dict)
            or not isinstance(entry.get("serial"), str)
            or not isinstance(entry.get("phone_name", ""), str)
            for entry in devices
        ) or any(not isinstance(serial, str) for serial in deleted):
            raise TypeError(
                f"Device inventory {self._inventory_path} has invalid device records"
            )
        return {"devices": devices, "deleted": deleted}

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
