import pytest
import yaml
from PySide6.QtWidgets import QApplication

from IGBot.core.device import AssignedAccount
from IGBot.services.account_assignment_service import AccountAssignmentService
from IGBot.ui.pages.account_page import AccountPage
from IGBot.ui.pages.like_configuration_page import LikeConfigurationPage


def configuration(tmp_path):
    directory = tmp_path / "accounts" / "account"
    directory.mkdir(parents=True)
    path = directory / "config.yml"
    path.write_bytes(
        b"# retained comment\r\n"
        b'username: "account"\r\n'
        b'device: "phone-a"\r\n'
        b"app-id: com.instagram.clone\r\n"
        b'likes-count: "1-2"\r\n'
        b'likes-percentage: "80-90"\r\n'
        b'total-likes-limit: "250" # retained inline\r\n'
        b"end-if-likes-limit-reached: false\r\n"
        b'carousel-count: "1"\r\n'
        b'carousel-percentage: "60-70"\r\n'
        b'watch-photo-time: "3-4"\r\n'
        b'watch-video-time: "15-30"\r\n'
        b"delete-interacted-users: false\r\n"
        b'posts-from-file: ["posts.txt"]\r\n'
        b"screen-sleep: true\r\n"
    )
    (directory / "filters.yml").write_bytes(
        b"# filter comment\r\n"
        b"min_likers: 10\r\n"
        b"max_likers: 900\r\n"
        b"mandatory_words: [cats]\r\n"
        b"blacklist_words: [spam]\r\n"
    )
    account = AssignedAccount("account", "phone-a", "com.instagram.clone", path)
    return AccountAssignmentService(tmp_path / "accounts"), account


def test_like_load_status_and_dirty_state(tmp_path):
    QApplication.instance() or QApplication([])
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    page.set_configuration(service.load_configuration(account.config_path))

    assert page.like_page.interaction.controls["likes-count"].text() == "1-2"
    assert page.like_page.media.controls["watch-video-time"].text() == "15-30"
    assert page.like_page.filters.controls["min_likers"].value() == 10
    assert page.like_page.likes_filter_enabled.isChecked()
    assert page.like_page.word_filters["mandatory_words"].entries() == ["cats"]
    assert page.tabs.tabText(4) == "Like"
    assert not page.is_dirty

    page.like_page.limits.controls["total-likes-limit"].setText("300")
    assert page.is_dirty


def test_like_methods_use_follow_checkbox_style():
    page = LikeConfigurationPage()

    for method in ("blogger-followers", "blogger"):
        row = page.sources.rows[method]
        assert row.enabled.objectName() != "configurationSwitch"
        assert row.name.objectName() == "checkboxLinkButton"


def test_like_save_uses_only_documented_engine_keys(tmp_path):
    service, account = configuration(tmp_path)
    page = LikeConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))
    page.interaction.controls["likes-count"].setText("2-3")
    page.limits.controls["total-likes-limit"].setText("300")
    page.limit_behaviour.controls["end-if-likes-limit-reached"].setChecked(True)
    page.filters.controls["min_likers"].setValue(25)
    page.delete_from_source.setChecked(True)
    page.files.controls["posts-from-file"].setPlainText("first.txt\nsecond.txt")

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    content = account.config_path.read_bytes()
    parsed = yaml.safe_load(content)
    assert parsed["likes-count"] == "2-3"
    assert parsed["total-likes-limit"] == "300"
    assert parsed["end-if-likes-limit-reached"] is True
    assert parsed["delete-interacted-users"] is True
    assert parsed["posts-from-file"] == ["first.txt", "second.txt"]
    assert parsed["screen-sleep"] is True
    assert b"# retained comment\r\n" in content
    assert b"# retained inline\r\n" in content
    assert not any(str(key).startswith("igbot-") for key in parsed)
    filters = yaml.safe_load((account.config_path.parent / "filters.yml").read_bytes())
    assert filters["min_likers"] == 25
    assert filters["max_likers"] == 900


def test_like_validation_rejects_ranges_and_percentages():
    QApplication.instance() or QApplication([])
    page = LikeConfigurationPage()
    page.set_configuration({})

    page.interaction.controls["likes-count"].setText("5-2")
    with pytest.raises(ValueError, match="ascending range"):
        page.values()

    page.interaction.controls["likes-count"].setText("1")
    page.interaction.controls["likes-percentage"].setText("101")
    with pytest.raises(ValueError, match="cannot exceed 100"):
        page.values()


def test_empty_like_page_does_not_create_engine_keys():
    page = LikeConfigurationPage()
    page.set_configuration({})

    assert page.values() == {}


def test_like_uses_follow_product_layout_and_hides_low_priority_controls():
    page = LikeConfigurationPage()

    assert page.enabled.text() == "Enable Like"
    assert page.sources.rows["blogger-followers"].name.text() == "Like Source Followers"
    assert page.sources.rows["blogger"].name.text() == "Like Posts of Specific Users"
    assert page.sources.rows["blogger-following"].isHidden()
    assert page.media.controls["carousel-count"].isHidden()
    assert page.media.controls["carousel-percentage"].isHidden()
    assert page.limit_behaviour.isHidden()
    assert page.schedule_section.body.isHidden()


def test_like_specific_users_uses_account_local_like_txt(tmp_path):
    service, account = configuration(tmp_path)
    page = AccountPage()
    page.set_account(account)
    configured = service.load_configuration(account.config_path)
    configured["blogger"] = ["first.user", "second.user"]

    page.set_configuration(configured)

    specific = account.config_path.parent / "Lists" / "likespecific.txt"
    assert specific.read_text(encoding="utf-8").splitlines() == [
        "first.user",
        "second.user",
    ]


def test_like_optional_filters_reveal_only_documented_controls():
    page = LikeConfigurationPage()
    page.set_configuration({})

    assert page.post_filter.isHidden()
    assert page.followers_filter.isHidden()
    assert page.followings_filter.isHidden()
    assert page.filters.isHidden()
    assert "max_posts" not in page.supported_keys()

    page.post_filter_enabled.setChecked(True)
    page.followers_filter_enabled.setChecked(True)
    page.followings_filter_enabled.setChecked(True)
    page.likes_filter_enabled.setChecked(True)

    assert not page.post_filter.isHidden()
    assert not page.followers_filter.isHidden()
    assert not page.followings_filter.isHidden()
    assert not page.filters.isHidden()


def test_like_additional_profile_filters_load_and_save_runtime_values():
    page = LikeConfigurationPage()
    page.set_configuration(
        {
            "mandatory_words": ["travel"],
            "blacklist_words": ["spam"],
            "specific_alphabet": ["latin", "greek"],
            "biography_language": ["en", "de"],
        }
    )

    assert tuple(page.word_filters) == (
        "mandatory_words",
        "blacklist_words",
        "specific_alphabet",
        "biography_language",
    )
    assert page.word_filters["specific_alphabet"].name.text() == "Allowed Alphabets"
    assert page.word_filters["biography_language"].name.text() == ("Biography Language")
    assert page.word_filters["specific_alphabet"].entries() == ["latin", "greek"]
    assert page.word_filters["biography_language"].entries() == ["en", "de"]
    assert page.values()["specific_alphabet"] == ["latin", "greek"]
    assert page.values()["biography_language"] == ["en", "de"]


def test_like_filters_and_behaviour_use_engine_keys_only(tmp_path):
    service, account = configuration(tmp_path)
    page = LikeConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    page.followers_filter_enabled.setChecked(True)
    page.followers_filter.controls["min_followers"].setValue(50)
    page.followers_filter.controls["max_followers"].setValue(5000)
    required = page.word_filters["mandatory_words"]
    required.set_entries(["cat", "pet lover"])
    required.enabled.setChecked(True)
    page._field_changed("mandatory_words")
    page.tagged_account_protection.setChecked(True)

    values = page.values()
    assert values["min_followers"] == 50
    assert values["max_followers"] == 5000
    assert values["mandatory_words"] == ["cat", "pet lover"]
    assert not any("tagged" in key for key in values)

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", values
    )
    filters = yaml.safe_load((account.config_path.parent / "filters.yml").read_bytes())
    assert filters["min_followers"] == 50
    assert filters["max_followers"] == 5000
    assert filters["mandatory_words"] == ["cat", "pet lover"]


def test_disabling_like_filter_removes_engine_filter_key(tmp_path):
    service, account = configuration(tmp_path)
    page = LikeConfigurationPage()
    page.set_configuration(service.load_configuration(account.config_path))

    page.likes_filter_enabled.setChecked(False)
    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", page.values()
    )

    filters = yaml.safe_load((account.config_path.parent / "filters.yml").read_bytes())
    assert "min_likers" not in filters
    assert "max_likers" not in filters


def test_like_action_fields_are_aligned_and_runtime_extensions_are_saved():
    page = LikeConfigurationPage()
    page.set_configuration({"likes-percentage": "100"})
    controls = (
        page.user_amount.minimum,
        page.user_amount.maximum,
        page.delay.minimum,
        page.delay.maximum,
        page.limits.controls["total-likes-limit"],
        page.interaction.controls["likes-count"],
        page.media.controls["watch-photo-time"],
        page.media.controls["watch-video-time"],
        page.interaction.controls["likes-percentage"],
    )

    assert all(control.width() == 180 for control in controls)
    page.user_amount.minimum.setValue(5)
    page.user_amount.maximum.setValue(10)
    page.delay.minimum.setValue(2)
    page.delay.maximum.setValue(6)
    page.schedule_days.controls["monday"].setChecked(False)

    values = page.values()
    extensions = page.runtime_extension_values()
    assert extensions == {
        "igbot-like-budget": "5-10",
        "igbot-like-action-delay": "2-6",
        "igbot-like-auto-increment-enabled": False,
        "igbot-like-auto-increment-by": "1",
        "igbot-like-auto-increment-maximum": "",
    }
    assert values["likes-percentage"] == "100"


def test_like_action_extensions_round_trip_through_account_metadata(tmp_path):
    service, account = configuration(tmp_path)
    page = LikeConfigurationPage()
    loaded = service.load_configuration(account.config_path)
    page.set_configuration(loaded)
    page.user_amount.minimum.setValue(4)
    page.user_amount.maximum.setValue(9)
    page.delay.minimum.setValue(3)
    page.delay.maximum.setValue(7)
    page.automatic_daily_increment.enabled.setChecked(True)
    page.automatic_daily_increment.increment.setText("4")
    page.automatic_daily_increment.maximum.setText("70")
    settings = page.values()
    settings.update(page.runtime_extension_values())

    service.update_configuration(
        account, "account", "secret", "com.instagram.clone", settings
    )
    restored = service.load_configuration(account.config_path)

    assert restored["igbot-like-budget"] == "4-9"
    assert restored["igbot-like-action-delay"] == "3-7"
    assert restored["igbot-like-auto-increment-enabled"] is True
    assert restored["igbot-like-auto-increment-by"] == "4"
    assert restored["igbot-like-auto-increment-maximum"] == "70"


@pytest.mark.parametrize(
    ("entered", "stored"), [("2", "2-2"), ("2-2", "2-2"), ("1-3", "1-3")]
)
def test_likes_per_profile_normalizes_fixed_values(entered, stored):
    page = LikeConfigurationPage()
    page.set_configuration({})
    page.interaction.controls["likes-count"].setText(entered)

    assert page.values()["likes-count"] == stored


def test_like_view_times_follow_likes_per_profile_in_action_grid():
    page = LikeConfigurationPage()

    positions = {}
    for key, control in (
        ("likes", page.interaction.controls["likes-count"]),
        ("photo", page.media.controls["watch-photo-time"]),
        ("video", page.media.controls["watch-video-time"]),
        ("percentage", page.interaction.controls["likes-percentage"]),
    ):
        index = page.action_grid.indexOf(control)
        positions[key] = page.action_grid.getItemPosition(index)[0]

    assert positions == {"likes": 2, "photo": 3, "video": 4, "percentage": 5}
    daily = page.limits.controls["total-likes-limit"]
    assert page.action_grid.getItemPosition(page.action_grid.indexOf(daily))[0] == 6
    assert page.limits.labels["total-likes-limit"].text() == "Daily Like Limit"
    assert page.action_grid.getItemPosition(
        page.action_grid.indexOf(page.like_limit_help)
    )[0] == 10
    assert page.like_limit_help.objectName() == "configurationHint"
    assert page.like_limit_help.text() == (
        "Daily hard limit. The bot will never exceed this number of likes per day."
    )


def test_like_automatic_daily_increment_enablement_and_range_validation():
    page = LikeConfigurationPage()
    page.set_configuration(
        {
            "igbot-like-auto-increment-enabled": True,
            "igbot-like-auto-increment-by": "2",
            "igbot-like-auto-increment-maximum": "60-80",
        }
    )
    automatic = page.automatic_daily_increment

    assert automatic.increment.isEnabled()
    assert automatic.maximum.isEnabled()
    assert automatic.values()["igbot-like-auto-increment-maximum"] == "60-80"

    automatic.maximum.setText("80-60")
    with pytest.raises(ValueError, match="ascending range"):
        page.runtime_extension_values()


def test_minimum_posts_is_a_single_left_aligned_numeric_field():
    page = LikeConfigurationPage()
    layout = page.post_filter.layout()
    label_index = layout.indexOf(page.post_filter.labels["min_posts"])
    control_index = layout.indexOf(page.post_filter.controls["min_posts"])

    assert layout.getItemPosition(label_index)[:2] == (0, 0)
    assert layout.getItemPosition(control_index)[:2] == (0, 1)
    assert page.post_filter.controls["min_posts"].width() == 180
