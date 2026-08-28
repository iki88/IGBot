import json
from pathlib import Path

import pytest
import yaml
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage


def _account(tmp_path, content=None):
    root = tmp_path / "accounts"
    directory = root / "original"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        (
            content
            or "# account settings\r\nusername: original # identity\r\n"
            'password: "old#password" # secret\r\n'
            "device: phone-a # assignment\r\n"
            "app-id: com.instagram.android # package\r\n"
            "screen-sleep: true\r\n"
        ).encode("utf-8")
    )
    return AccountAssignmentService(root), AssignedAccount(
        "original", "phone-a", "com.instagram.android", path
    )


def test_overview_contains_only_unified_account_information(tmp_path):
    application = QApplication.instance() or QApplication([])
    service, account = _account(tmp_path)
    page = AccountPage()
    page.set_account(account, "T1")
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.username.text() == "original"
    assert page.password.text() == "old#password"
    assert page.password.echoMode() == QLineEdit.Password
    assert page.application_id.text() == "com.instagram.android"
    assert page.detect_app_id_button.isEnabled()
    assert page.detect_app_id_button.text() == "Detect"
    assert page.detect_app_id_button.toolTip() == "Detect App ID"
    assert not hasattr(page, "load_app_ids_button")
    assert not hasattr(page, "login_button")
    assert not hasattr(page, "logout_button")
    assert page.tag.text() == ""
    assert page.tag.placeholderText() == "Warmup, APK1, VIP, Client A, Germany"
    overview_text = page.tabs.widget(0).widget().findChildren(QLineEdit)
    assert set(overview_text) == {
        page.username,
        page.password,
        page.application_id,
        page.tag,
    }
    page.password_toggle.setChecked(True)
    assert page.password.echoMode() == QLineEdit.Normal
    assert page.password_toggle.toolTip() == "Hide password"
    assert application is not None


def test_detect_button_shares_the_application_field_row():
    page = AccountPage()

    assert page.application_layout.indexOf(page.application_id) == 0
    assert page.application_layout.indexOf(page.detect_app_id_button) == 1
    assert page.application_layout.contentsMargins().left() == 0
    assert page.application_layout.spacing() == 8


def test_detect_button_emits_detection_request_and_updates_field(tmp_path):
    QApplication.instance() or QApplication([])
    page = AccountPage()
    requests = []
    page.package_detection_requested.connect(lambda: requests.append(True))

    page.detect_app_id_button.click()
    page.set_application_id("com.instagram.detected")

    assert requests == [True]
    assert page.application_id.text() == "com.instagram.detected"
    assert page.is_dirty


def test_application_id_remains_editable_after_detection_and_supports_paste():
    application = QApplication.instance() or QApplication([])
    page = AccountPage()
    page.set_application_id("com.instagram.detected")

    assert not page.application_id.isReadOnly()
    page.application_id.setFocus()
    QTest.keyClick(page.application_id, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(page.application_id, "com.instagram.manual")
    assert page.application_id.text() == "com.instagram.manual"

    application.clipboard().setText("com.instagram.pasted")
    QTest.keyClick(page.application_id, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClick(page.application_id, Qt.Key_V, Qt.ControlModifier)
    assert page.application_id.text() == "com.instagram.pasted"


def test_manually_entered_application_id_persists_after_restart(tmp_path):
    service, account = _account(tmp_path)

    updated = service.update_configuration(
        account, "original", "secret", "com.instagram.manual"
    )
    restarted = AccountAssignmentService(service.accounts_directory)

    assert restarted.load_configuration(updated.config_path)["app-id"] == (
        "com.instagram.manual"
    )


def test_save_preserves_comments_line_endings_and_unrelated_configuration(tmp_path):
    service, account = _account(tmp_path)

    updated = service.update_configuration(
        account, "renamed.account", "new:password#2", "com.instagram.clone"
    )

    content = updated.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert updated.username == "renamed.account"
    assert updated.config_path.parent.name == "renamed.account"
    assert not account.config_path.parent.exists()
    assert "password" not in parsed
    assert parsed["app-id"] == "com.instagram.clone"
    assert parsed["device"] == "phone-a"
    assert parsed["screen-sleep"] is True
    assert b"# identity\r\n" in content
    assert b"# assignment\r\n" in content
    assert b"# package\r\n" in content
    assert content.replace(b"\r\n", b"").find(b"\n") == -1
    metadata = json.loads(
        (updated.config_path.parent / "account.json").read_text(encoding="utf-8")
    )
    assert metadata["username"] == "renamed.account"
    assert metadata["password"] == "new:password#2"
    assert metadata["assigned_device_id"] == "phone-a"
    assert metadata["created_at"]


def test_save_does_not_add_unsupported_password_key(tmp_path):
    service, account = _account(
        tmp_path,
        "username: original # identity\n"
        "device: phone-a\n"
        "app-id: com.instagram.android\n",
    )

    service.update_configuration(account, "original", "new-secret", account.app_id)

    assert account.config_path.read_text(encoding="utf-8") == (
        "username: original # identity\n"
        "device: phone-a\n"
        "app-id: com.instagram.android\n"
    )
    metadata = json.loads(
        (account.config_path.parent / "account.json").read_text(encoding="utf-8")
    )
    assert metadata["password"] == "new-secret"


def test_credentials_persist_when_service_is_restarted(tmp_path):
    service, account = _account(
        tmp_path,
        "username: original\ndevice: phone-a\napp-id: com.instagram.android\n",
    )
    service.update_configuration(
        account, "original", "persistent-secret", account.app_id
    )

    restarted = AccountAssignmentService(service.accounts_directory)
    configuration = restarted.load_configuration(account.config_path)

    assert configuration["username"] == "original"
    assert configuration["password"] == "persistent-secret"


def test_detected_application_id_persists_after_restart(tmp_path):
    service, account = _account(tmp_path)

    updated = service.update_configuration(
        account, "original", "secret", "com.instagram.detected"
    )
    restarted = AccountAssignmentService(service.accounts_directory)
    configuration = restarted.load_configuration(updated.config_path)

    assert configuration["app-id"] == "com.instagram.detected"
    assert restarted.load_by_device()["phone-a"][0].app_id == "com.instagram.detected"


def test_metadata_updates_preserve_created_timestamp_and_extension_fields(tmp_path):
    service, account = _account(tmp_path)
    updated = service.update_configuration(account, "original", "first", account.app_id)
    metadata_path = updated.config_path.parent / "account.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["notes"] = "operator-owned metadata"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    service.update_configuration(updated, "original", "second", account.app_id)
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert saved["password"] == "second"
    assert saved["created_at"] == metadata["created_at"]
    assert saved["notes"] == "operator-owned metadata"


def test_tag_persists_in_metadata_and_reloads(tmp_path):
    service, account = _account(tmp_path)

    updated = service.update_configuration(
        account,
        "original",
        "secret",
        account.app_id,
        tag="priority-group",
    )
    metadata_path = updated.config_path.parent / "account.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["tag"] == "priority-group"
    assert service.load_configuration(updated.config_path)["tag"] == "priority-group"
    assert "tag" not in yaml.safe_load(updated.config_path.read_bytes())


def test_saving_without_tag_preserves_existing_metadata_tag(tmp_path):
    service, account = _account(tmp_path)
    updated = service.update_configuration(
        account, "original", "first", account.app_id, tag="account-only"
    )

    service.update_configuration(updated, "original", "second", account.app_id)

    metadata = json.loads(
        (updated.config_path.parent / "account.json").read_text(encoding="utf-8")
    )
    assert metadata["tag"] == "account-only"


@pytest.mark.parametrize(
    ("username", "password", "app_id", "message"),
    (
        ("invalid name", "secret", "com.instagram.android", "username"),
        ("original", "secret", "invalid", "application ID"),
    ),
)
def test_save_rejects_invalid_values_without_modifying_configuration(
    tmp_path, username, password, app_id, message
):
    service, account = _account(tmp_path)
    original = account.config_path.read_bytes()

    with pytest.raises(ValueError, match=message):
        service.update_configuration(account, username, password, app_id)

    assert account.config_path.read_bytes() == original


def test_save_rejects_duplicate_username(tmp_path):
    service, account = _account(tmp_path)
    duplicate = tmp_path / "accounts" / "duplicate"
    duplicate.mkdir()
    (duplicate / "config.yml").write_text(
        "username: Existing\ndevice: phone-b\napp-id: com.instagram.android\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already exists"):
        service.update_configuration(
            account, "existing", "secret", "com.instagram.android"
        )
    assert not (account.config_path.parent / "account.json").exists()


def test_save_restores_original_after_verification_failure(tmp_path, mocker):
    service, account = _account(tmp_path)
    original = account.config_path.read_bytes()
    writer = service._write_configuration
    calls = 0

    def corrupt_first_write(path: Path, content: str):
        nonlocal calls
        calls += 1
        writer(path, "invalid: true\n" if calls == 1 else content)

    mocker.patch.object(
        service, "_write_configuration", side_effect=corrupt_first_write
    )

    with pytest.raises(RuntimeError, match="original was restored"):
        service.update_configuration(
            account, "original", "new-password", "com.instagram.android"
        )

    assert account.config_path.read_bytes() == original
