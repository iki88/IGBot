from io import StringIO

from IGBot.tools.inspect_instagram_ui import inspect_device


class FakeDevice:
    serial = "device-123"

    def app_current(self):
        return {
            "package": "com.instagram.clone",
            "activity": ".MainActivity",
        }

    def dump_hierarchy(self, **options):
        assert options == {"compressed": False}
        return (
            '<hierarchy rotation="0">'
            '<node class="android.widget.TextView" text="visible_user" '
            'content-desc="Profile username" '
            'resource-id="com.instagram.clone:id/profile_username" '
            'bounds="[10,20][200,80]" visible-to-user="true" />'
            '<node class="android.widget.TextView" text="hidden" '
            'bounds="[0,0][0,0]" visible-to-user="false" />'
            "</hierarchy>"
        )


def test_inspection_writes_hierarchy_and_readable_visible_summary(tmp_path):
    destination = tmp_path / "instagram_ui.xml"
    output = StringIO()
    calls = []

    def connector(serial):
        calls.append(serial)
        return FakeDevice()

    result = inspect_device(
        "device-123",
        connector=connector,
        destination=destination,
        output=output,
    )

    assert result == destination
    assert destination.is_file()
    assert "visible_user" in destination.read_text(encoding="utf-8")
    assert calls == ["device-123"]
    report = output.getvalue()
    assert "Connected device serial: device-123" in report
    assert "Current foreground package: com.instagram.clone" in report
    assert "Current activity: .MainActivity" in report
    assert "Visible nodes (1):" in report
    assert "class='android.widget.TextView'" in report
    assert "text='visible_user'" in report
    assert "content-desc='Profile username'" in report
    assert "resource-id='com.instagram.clone:id/profile_username'" in report
    assert "bounds='[10,20][200,80]'" in report
    assert "hidden" not in report
    assert "Hierarchy saved successfully:" in report


def test_inspection_uses_uiautomator_single_device_selection(tmp_path):
    received = []

    inspect_device(
        connector=lambda serial: received.append(serial) or FakeDevice(),
        destination=tmp_path / "instagram_ui.xml",
        output=StringIO(),
    )

    assert received == [None]
