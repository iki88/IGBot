"""Session Startup stage that verifies Instagram account identity."""

from __future__ import annotations

from IGBot.runtime.account_verification import (
    InstagramProfileProvider,
    ProfileObservationState,
)
from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.notifications import (
    RuntimeNotification,
    RuntimeNotificationLevel,
    RuntimeNotifier,
)
from IGBot.runtime.startup.models import (
    AccountVerificationState,
    StartupStageName,
    StartupStageResult,
    StartupStageStatus,
)
from IGBot.runtime.state import SessionState


class AccountVerifier:
    """Compare the complete loaded Instagram username with session identity."""

    def __init__(
        self,
        provider: InstagramProfileProvider,
        notifier: RuntimeNotifier,
    ) -> None:
        self._provider = provider
        self._notifier = notifier

    def execute(self, context: RuntimeContext) -> StartupStageResult:
        """Open Profile, resolve complete identity, and return a domain result."""
        expected = context.session.account_username.strip()
        context.logger.info("Verifying Instagram account", expected_username=expected)
        try:
            observation = self._provider.open_profile(context)
        except Exception as error:  # noqa: BLE001 - provider isolation boundary
            return self._failed(
                context,
                AccountVerificationState.PROFILE_NOT_LOADED,
                f"Instagram Profile provider failed: {error}",
            )

        if observation.state is ProfileObservationState.PROFILE_NOT_AVAILABLE:
            return self._failed(
                context,
                AccountVerificationState.PROFILE_NOT_AVAILABLE,
                observation.detail or "Instagram Profile is not available.",
            )
        if observation.state is ProfileObservationState.PROFILE_NOT_LOADED:
            return self._failed(
                context,
                AccountVerificationState.PROFILE_NOT_LOADED,
                observation.detail or "Instagram Profile did not load.",
            )

        detected = observation.username
        if observation.state is ProfileObservationState.USERNAME_TRUNCATED:
            context.logger.info(
                "Profile username is truncated; opening Account Switcher"
            )
            try:
                complete = self._provider.complete_username_from_switcher(context)
            except Exception as error:  # noqa: BLE001 - provider isolation boundary
                return self._failed(
                    context,
                    AccountVerificationState.PROFILE_NOT_LOADED,
                    f"Account Switcher provider failed: {error}",
                )
            if not complete.username:
                return self._failed(
                    context,
                    AccountVerificationState.PROFILE_NOT_LOADED,
                    complete.detail
                    or "Account Switcher did not expose a complete username.",
                )
            detected = complete.username

        if not detected:
            return self._failed(
                context,
                AccountVerificationState.PROFILE_NOT_LOADED,
                "Instagram Profile did not expose a username.",
            )

        detected = detected.strip()
        if detected.casefold() != expected.casefold():
            return self._mismatch(context, expected, detected)

        context.logger.info("Instagram account verified", detected_username=detected)
        return StartupStageResult(
            StartupStageName.ACCOUNT_VERIFICATION,
            StartupStageStatus.SUCCESS,
            account_verified=True,
            account_verification=AccountVerificationState.VERIFIED,
            detected_username=detected,
        )

    def _mismatch(
        self,
        context: RuntimeContext,
        expected: str,
        detected: str,
    ) -> StartupStageResult:
        context.session_state = SessionState.WAITING_FOR_OPERATOR
        context.logger.warning(
            "Instagram username mismatch",
            expected_username=expected,
            detected_username=detected,
        )
        notification = RuntimeNotification(
            title="Instagram username mismatch",
            message=(
                f"Expected: {expected}\nDetected: {detected}\n\n"
                "Suggested operator action: Update the username in IGBot."
            ),
            level=RuntimeNotificationLevel.WARNING,
        )
        try:
            self._notifier.notify(context, notification)
        except Exception as error:  # noqa: BLE001 - notification isolation boundary
            context.logger.error(f"Runtime notification failed: {error}")
        return StartupStageResult(
            StartupStageName.ACCOUNT_VERIFICATION,
            StartupStageStatus.FAILED,
            detail=(
                f"Expected Instagram username {expected}, but detected {detected}."
            ),
            account_verified=False,
            account_verification=AccountVerificationState.USERNAME_MISMATCH,
            detected_username=detected,
        )

    @staticmethod
    def _failed(
        context: RuntimeContext,
        state: AccountVerificationState,
        detail: str,
    ) -> StartupStageResult:
        context.logger.error(detail)
        return StartupStageResult(
            StartupStageName.ACCOUNT_VERIFICATION,
            StartupStageStatus.FAILED,
            detail=detail,
            account_verified=False,
            account_verification=state,
        )
