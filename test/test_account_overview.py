from pathlib import Path

import pytest
import yaml
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


def test_overview_masks_password_and_disables_future_operations(tmp_path):
    application = QApplication.instance() or QApplication([])
    service, account = _account(tmp_path)
    page = AccountPage()
    page.set_account(account, "T1")
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.username.text() == "original"
    assert page.password.text() == "old#password"
    assert page.password.echoMode() == QLineEdit.Password
    assert page.application_id.text() == "com.instagram.android"
    assert not any(
        button.isEnabled()
        for button in (
            page.login_button,
            page.logout_button,
            page.detect_app_id_button,
            page.load_app_ids_button,
        )
    )
    page.password_toggle.setChecked(True)
    assert page.password.echoMode() == QLineEdit.Normal
    assert page.password_toggle.text() == "Hide"
    assert application is not None


def test_save_preserves_comments_line_endings_and_unrelated_configuration(tmp_path):
    service, account = _account(tmp_path)

    updated = service.update_configuration(
        account, "renamed.account", "new:password#2", "com.instagram.clone"
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert updated.username == "renamed.account"
    assert parsed["password"] == "new:password#2"
    assert parsed["app-id"] == "com.instagram.clone"
    assert parsed["device"] == "phone-a"
    assert parsed["screen-sleep"] is True
    assert b"# identity\r\n" in content
    assert b"# secret\r\n" in content
    assert b"# assignment\r\n" in content
    assert b"# package\r\n" in content
    assert content.replace(b"\r\n", b"").find(b"\n") == -1


def test_save_adds_missing_password_without_changing_other_lines(tmp_path):
    service, account = _account(
        tmp_path,
        "username: original # identity\n"
        "device: phone-a\n"
        "app-id: com.instagram.android\n",
    )

    service.update_configuration(account, "original", "new-secret", account.app_id)

    assert account.config_path.read_text(encoding="utf-8") == (
        "username: original # identity\n"
        'password: "new-secret"\n'
        "device: phone-a\n"
        "app-id: com.instagram.android\n"
    )


@pytest.mark.parametrize(
    ("username", "password", "app_id", "message"),
    (
        ("invalid name", "secret", "com.instagram.android", "username"),
        ("original", "", "com.instagram.android", "password"),
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
