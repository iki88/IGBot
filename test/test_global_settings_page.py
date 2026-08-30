from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLabel,
    QScrollArea,
    QToolButton,
)

from IGBot.ui.pages.global_settings_page import GlobalSettingsPage
from IGBot.ui.widgets.configuration_widgets import ConfigurationSection


def test_global_settings_uses_continuous_product_layout(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)

    assert isinstance(page, QScrollArea)
    assert page.widgetResizable()
    assert [
        section.title.text() for section in page.findChildren(ConfigurationSection)
    ] == [
        "Session Startup",
        "Runtime Safety",
        "Hourly Limits",
        "Contact Details",
        "AI",
        "Integrations",
    ]


def test_global_settings_exposes_requested_operator_controls(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)

    assert page.airplane_mode_reset.text() == "Toggle Airplane Mode Between Sessions"
    assert page.random_search_letters.text() == "Use Random Search Letters"
    assert page.enable_block_detection.text() == "Enable Block Detection"
    runtime_safety = next(
        section
        for section in page.findChildren(ConfigurationSection)
        if section.title.text() == "Runtime Safety"
    )
    assert runtime_safety.isAncestorOf(page.random_search_letters)
    assert runtime_safety.isAncestorOf(page.airplane_mode_reset)
    assert page.first_character_pool.text() == "abcdefghijklmnopqrstuvwxyz"
    assert page.second_character_pool.text() == "aeiou"
    assert page.follow_back_ratio_check.text() == "Enable Follow Back Ratio Check"
    assert page.follow_back_ratio_check.isChecked()
    assert page.contact_details_scraping.text() == ("Enable Contact Details Scraping")
    assert page.backend_api_integration.text() == "Backend API"
    assert page.ai_provider.count() == 1
    assert page.ai_provider.currentText() == "OpenAI"
    assert set(page.hourly_limits) == {
        "follows",
        "unfollows",
        "likes",
        "dms",
        "story_views",
        "comments",
    }
    assert not hasattr(page, "restart_instagram_automatically")
    assert not hasattr(page, "screen_recording")
    assert not hasattr(page, "website_api_integration")
    assert not hasattr(page, "after_scrolling_timeout")
    assert not hasattr(page, "mongodb_integration")
    assert not hasattr(page, "telegram_integration")


def test_only_documented_engine_controls_have_engine_bindings(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)

    assert page.enable_block_detection.property("engineKey") == (
        "disable-block-detection"
    )
    assert page.maximum_crash_retries.property("engineKey") == ("total-crashes-limit")
    assert "enable_block_detection" in page.INVERTED_ENGINE_BINDINGS

    runtime_extensions = (
        page.start_all_phones_delay,
        page.wait_after_instagram_launch,
        page.login_retry_limit,
        page.airplane_mode_reset,
        page.random_search_letters,
        page.pause_after_action_block,
        page.maximum_scrolling_time,
        page.first_character_pool,
        page.second_character_pool,
        page.follow_back_ratio_check,
        page.contact_details_scraping,
        page.ai_provider,
        page.ai_model,
        page.openai_api_key,
        page.temperature,
        page.backend_api_integration,
        *page.hourly_limits.values(),
    )
    assert all(control.property("runtimeExtension") for control in runtime_extensions)
    assert all(control.property("engineKey") is None for control in runtime_extensions)


def test_global_numeric_controls_are_compact_and_wheel_safe(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)
    controls = (
        page.start_all_phones_delay,
        page.login_retry_limit,
        page.pause_after_action_block,
        page.maximum_crash_retries,
        page.maximum_scrolling_time,
        *page.hourly_limits.values(),
    )

    assert all(control.width() == 180 for control in controls)
    assert all(
        control.buttonSymbols() == QAbstractSpinBox.NoButtons for control in controls
    )
    assert page.verticalScrollBarPolicy() in (
        Qt.ScrollBarAsNeeded,
        Qt.ScrollBarAlwaysOff,
    )


def test_launch_wait_accepts_fixed_or_range_values(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)
    editor = page.wait_after_instagram_launch

    editor.setText("10")
    assert editor.hasAcceptableInput()
    editor.setText("8-12")
    assert editor.hasAcceptableInput()
    editor.setText("8 to 12")
    assert not editor.hasAcceptableInput()
    assert editor.width() == 180


def test_advanced_global_controls_have_help_tooltips(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)
    tooltips = {
        button.toolTip()
        for button in page.findChildren(QToolButton, "settingInfoButton")
    }

    assert any("new mobile IP address" in tooltip for tooltip in tooltips)
    assert any("Random prefixes" in tooltip for tooltip in tooltips)
    assert any("endless user search" in tooltip for tooltip in tooltips)
    assert any("Follow Back Ratio (FBR)" in tooltip for tooltip in tooltips)


def test_global_settings_uses_compact_information_tooltips(tmp_path):
    QApplication.instance() or QApplication([])
    page = GlobalSettingsPage(tmp_path)
    info_buttons = page.findChildren(QToolButton, "settingInfoButton")

    assert info_buttons
    assert all(button.text() == "ⓘ" for button in info_buttons)
    assert all(button.toolTip().strip() for button in info_buttons)
    assert not page.findChildren(QLabel, "configurationDescription")
