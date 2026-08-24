import json

from IGBot.core.phone_manager import DeviceDiscoveryResult
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.services.device_inventory_service import DeviceInventoryService


def _service(tmp_path):
    accounts_directory = tmp_path / "accounts"
    accounts_directory.mkdir()
    return DeviceInventoryService(
        inventory_path=tmp_path / "data" / "devices.json",
        account_assignments=AccountAssignmentService(accounts_directory),
    )


def test_refresh_preserves_manual_order_and_marks_disconnected_phone_offline(
    tmp_path, mocker
):
    service = _service(tmp_path)
    discover = mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        side_effect=[
            DeviceDiscoveryResult(["phone-b", "phone-a"]),
            DeviceDiscoveryResult(["phone-a"]),
        ],
    )

    first = service.refresh()
    second = service.refresh()

    assert [device.serial for device in first.devices] == ["phone-b", "phone-a"]
    assert [device.serial for device in second.devices] == ["phone-b", "phone-a"]
    assert second.devices[0].connected is False
    assert second.devices[0].status == "Offline"
    assert second.devices[1].connected is True
    assert discover.call_count == 2


def test_refresh_counts_only_real_assigned_accounts(tmp_path, mocker):
    accounts_directory = tmp_path / "accounts"
    assigned = accounts_directory / "assigned"
    unassigned = accounts_directory / "unassigned"
    assigned.mkdir(parents=True)
    unassigned.mkdir()
    (assigned / "config.yml").write_text(
        "username: real_account\ndevice: phone-a\napp-id: com.instagram.android\n",
        encoding="utf-8",
    )
    (unassigned / "config.yml").write_text("username: not_assigned\n", encoding="utf-8")
    service = DeviceInventoryService(
        inventory_path=tmp_path / "devices.json",
        account_assignments=AccountAssignmentService(accounts_directory),
    )
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        return_value=DeviceDiscoveryResult(["phone-a"]),
    )

    snapshot = service.refresh()

    assert [account.username for account in snapshot.devices[0].accounts] == [
        "real_account"
    ]


def test_delete_suppresses_connected_phone_until_it_disconnects(tmp_path, mocker):
    service = _service(tmp_path)
    mocker.patch(
        "IGBot.services.device_inventory_service.PhoneManager.discover_devices",
        side_effect=[
            DeviceDiscoveryResult(["phone-a"]),
            DeviceDiscoveryResult(["phone-a"]),
            DeviceDiscoveryResult([]),
            DeviceDiscoveryResult(["phone-a"]),
        ],
    )
    service.refresh()
    service.delete("phone-a", connected=True)
    while_connected = service.refresh()
    after_disconnect = service.refresh()
    after_reconnect = service.refresh()

    assert while_connected.devices == ()
    assert after_disconnect.devices == ()
    assert [device.serial for device in after_reconnect.devices] == ["phone-a"]
    saved = json.loads((tmp_path / "data" / "devices.json").read_text())
    assert saved["suppressed"] == []
