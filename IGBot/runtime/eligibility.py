"""Native runtime eligibility boundary consumed by the phone scheduler."""

from __future__ import annotations

from collections.abc import Mapping

from IGBot.core.device import AssignedAccount
from IGBot.runtime.follow.daily_limits import remaining_daily_follows


def _enabled(value: object) -> bool:
    return value not in (None, False, 0, "", "0")


def _has_usernames(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(str(username).strip() for username in value)
    return False


def follow_provider_is_configured(configuration: Mapping[str, object]) -> bool:
    """Match the native Follow factory's provider selection and readiness rules."""

    specific_users = configuration.get("blogger")
    if _enabled(specific_users):
        return _has_usernames(specific_users)
    return any(
        _has_usernames(configuration.get(key))
        for key in ("blogger-followers", "blogger-following")
    )


def native_follow_configuration_ready(configuration: Mapping[str, object]) -> bool:
    """Report whether Follow is enabled with one complete native provider."""

    return _enabled(
        configuration.get("follow-percentage")
    ) and follow_provider_is_configured(configuration)


def native_account_is_runnable(
    account: AssignedAccount, configuration: Mapping[str, object]
) -> bool:
    """Report whether any implemented native interaction module can run now."""

    return (
        native_follow_configuration_ready(configuration)
        and remaining_daily_follows(
            account.config_path.parent,
            configuration.get("total-follows-limit"),
        )
        > 0
    )
