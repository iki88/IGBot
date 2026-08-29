from pathlib import Path
from typing import ClassVar

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from IGBot.ui.widgets.configuration_widgets import (
    ConfigurationSection,
    WheelSafeDoubleSpinBox,
    WheelSafeSpinBox,
)
from IGBot.ui.widgets.page_header import PageHeader


class GlobalSettingsPage(QScrollArea):
    """Operator-focused global settings presentation.

    Sprint 5.22 intentionally provides no persistence layer. Controls backed by
    the legacy engine are identified in ``ENGINE_BINDINGS``; all other controls
    are IGBot runtime-extension designs and must not be written to account YAML.
    """

    ENGINE_BINDINGS: ClassVar[dict[str, str]] = {
        "enable_block_detection": "disable-block-detection",
        "maximum_crash_retries": "total-crashes-limit",
    }
    INVERTED_ENGINE_BINDINGS: ClassVar[frozenset[str]] = frozenset(
        {"enable_block_detection"}
    )

    def __init__(self, workspace: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.setObjectName("globalSettingsPage")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)

        container = QWidget(self)
        container.setObjectName("globalSettingsContent")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        layout.addWidget(
            PageHeader(
                "Global Settings",
                "Application-wide defaults, runtime safety, and integrations.",
                container,
            )
        )
        layout.addWidget(self._build_session_startup(container))
        layout.addWidget(self._build_runtime_safety(container))
        layout.addWidget(self._build_hourly_limits(container))
        layout.addWidget(self._build_contact_details(container))
        layout.addWidget(self._build_ai(container))
        layout.addWidget(self._build_integrations(container))
        layout.addStretch()
        self.setWidget(container)

    def _build_session_startup(self, parent: QWidget) -> ConfigurationSection:
        section = ConfigurationSection("Session Startup", parent)
        grid = self._settings_grid(section)
        self.start_all_phones_delay = self._numeric_control(
            section, maximum=3600, suffix=" sec"
        )
        self.start_all_phones_delay.setProperty("runtimeExtension", True)
        self.wait_after_instagram_launch = self._numeric_control(
            section, maximum=3600, suffix=" sec"
        )
        self.wait_after_instagram_launch.setProperty("runtimeExtension", True)
        self.login_retry_limit = self._numeric_control(section, maximum=100)
        self.login_retry_limit.setProperty("runtimeExtension", True)
        self.airplane_mode_reset = self._switch(
            "Enable Airplane Mode Reset", section, runtime_extension=True
        )
        self.random_search_letters = self._switch(
            "Enable Random Search Letters", section, runtime_extension=True
        )

        self._add_field(
            grid,
            0,
            "Start All Phones Delay",
            self.start_all_phones_delay,
            info="Time between phone starts when Start All is used.",
        )
        self._add_field(
            grid,
            1,
            "Wait After Launching Instagram",
            self.wait_after_instagram_launch,
            info="Time before automation begins after Instagram opens.",
        )
        self._add_field(
            grid,
            2,
            "Login Retry Limit Per Day",
            self.login_retry_limit,
            info="Maximum automatic attempts before operator intervention.",
        )
        grid.addWidget(self.airplane_mode_reset, 3, 0, 1, 3)
        return section

    def _build_runtime_safety(self, parent: QWidget) -> ConfigurationSection:
        section = ConfigurationSection("Runtime Safety", parent)
        grid = self._settings_grid(section)
        self.enable_block_detection = self._switch(
            "Enable Block Detection", section, engine_key="disable-block-detection"
        )
        self.pause_after_action_block = self._numeric_control(
            section, maximum=10080, suffix=" min"
        )
        self.pause_after_action_block.setProperty("runtimeExtension", True)
        self.maximum_scrolling_time = self._numeric_control(
            section, maximum=10080, suffix=" min"
        )
        self.maximum_scrolling_time.setProperty("runtimeExtension", True)
        self.maximum_crash_retries = self._numeric_control(section, maximum=100)
        self.maximum_crash_retries.setProperty(
            "engineKey", self.ENGINE_BINDINGS["maximum_crash_retries"]
        )
        grid.addWidget(self.enable_block_detection, 0, 0, 1, 3)
        self._add_field(
            grid,
            1,
            "Pause Automation After Action Block",
            self.pause_after_action_block,
            info="Cooldown after an Instagram action block is detected.",
        )
        self._add_field(
            grid,
            2,
            "Maximum Crash Retries",
            self.maximum_crash_retries,
            info="Maximum recoverable crashes before the session stops.",
        )
        grid.addWidget(self.random_search_letters, 3, 0, 1, 3)
        self._add_field(
            grid,
            4,
            "Maximum Scrolling Time",
            self.maximum_scrolling_time,
            info=(
                "Stops an endless user search after this time so another "
                "discovery strategy can be used."
            ),
        )
        return section

    def _build_hourly_limits(self, parent: QWidget) -> ConfigurationSection:
        section = ConfigurationSection("Hourly Limits", parent)
        grid = self._settings_grid(section)
        self.hourly_limits = {}
        labels = (
            ("follows", "Maximum Follows Per Hour"),
            ("unfollows", "Maximum Unfollows Per Hour"),
            ("likes", "Maximum Likes Per Hour"),
            ("dms", "Maximum DMs Per Hour"),
            ("story_views", "Maximum Story Views Per Hour"),
            ("comments", "Maximum Comments Per Hour"),
        )
        for row, (name, label) in enumerate(labels):
            control = self._numeric_control(section, maximum=100000)
            control.setProperty("runtimeExtension", True)
            self.hourly_limits[name] = control
            self._add_field(grid, row, label, control)
        return section

    def _build_contact_details(self, parent: QWidget) -> ConfigurationSection:
        section = ConfigurationSection("Contact Details", parent)
        self.contact_details_scraping = self._switch(
            "Enable Contact Details Scraping", section, runtime_extension=True
        )
        section.body_layout.addWidget(
            self._switch_row(
                self.contact_details_scraping,
                (
                    "Collects available email, phone, website, and business "
                    "contact information into the account database."
                ),
            )
        )
        return section

    def _build_ai(self, parent: QWidget) -> ConfigurationSection:
        section = ConfigurationSection("AI", parent)
        grid = self._settings_grid(section)
        self.ai_provider = QComboBox(section)
        self.ai_provider.addItem("Not configured", None)
        self.ai_model = QLineEdit(section)
        self.ai_model.setPlaceholderText("Model name")
        self.openai_api_key = QLineEdit(section)
        self.openai_api_key.setEchoMode(QLineEdit.Password)
        self.openai_api_key.setPlaceholderText("API key")
        self.temperature = WheelSafeDoubleSpinBox(section)
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setDecimals(1)
        for control in (
            self.ai_provider,
            self.ai_model,
            self.openai_api_key,
            self.temperature,
        ):
            control.setFixedWidth(260)
            control.setProperty("runtimeExtension", True)

        self._add_field(grid, 0, "AI Provider", self.ai_provider)
        self._add_field(grid, 1, "AI Model", self.ai_model)
        self._add_field(grid, 2, "OpenAI API Key", self.openai_api_key)
        self._add_field(grid, 3, "Temperature", self.temperature)
        return section

    def _build_integrations(self, parent: QWidget) -> ConfigurationSection:
        section = ConfigurationSection("Integrations", parent)
        self.mongodb_integration = self._switch(
            "MongoDB", section, runtime_extension=True
        )
        self.backend_api_integration = self._switch(
            "Backend API", section, runtime_extension=True
        )
        self.telegram_integration = self._switch(
            "Telegram (optional)", section, runtime_extension=True
        )
        section.body_layout.addWidget(self.mongodb_integration)
        section.body_layout.addWidget(
            self._switch_row(
                self.backend_api_integration,
                (
                    "Connects IGBot to the backend for account intake, analytics, "
                    "runtime status, synchronization, and remote management."
                ),
            )
        )
        section.body_layout.addWidget(self.telegram_integration)
        return section

    @staticmethod
    def _settings_grid(section: ConfigurationSection) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(2, 1)
        section.body_layout.addLayout(grid)
        return grid

    @staticmethod
    def _numeric_control(
        parent: QWidget, *, maximum: int, suffix: str = ""
    ) -> WheelSafeSpinBox:
        control = WheelSafeSpinBox(parent)
        control.setRange(0, maximum)
        control.setSuffix(suffix)
        control.setFixedWidth(180)
        return control

    @staticmethod
    def _switch(
        label: str,
        parent: QWidget,
        *,
        engine_key: str | None = None,
        runtime_extension: bool = False,
    ) -> QCheckBox:
        control = QCheckBox(label, parent)
        control.setObjectName("configurationSwitch")
        if engine_key is not None:
            control.setProperty("engineKey", engine_key)
        if runtime_extension:
            control.setProperty("runtimeExtension", True)
        return control

    @staticmethod
    def _add_field(
        layout: QGridLayout,
        row: int,
        label: str,
        control: QWidget,
        info: str | None = None,
    ) -> None:
        heading = QWidget(control.parentWidget())
        heading_layout = QHBoxLayout(heading)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(5)
        heading_layout.addWidget(QLabel(label, heading))
        if info:
            heading_layout.addWidget(GlobalSettingsPage._info_button(info, heading))
        heading_layout.addStretch()
        layout.addWidget(heading, row, 0)
        layout.addWidget(control, row, 1)

    @staticmethod
    def _switch_row(control: QCheckBox, info: str) -> QWidget:
        row = QWidget(control.parentWidget())
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(control)
        layout.addWidget(GlobalSettingsPage._info_button(info, row))
        layout.addStretch()
        return row

    @staticmethod
    def _info_button(tool_tip: str, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName("settingInfoButton")
        button.setText("ⓘ")
        button.setToolTip(tool_tip)
        button.setAutoRaise(True)
        return button
