"""Sequential Session Startup orchestration."""

from __future__ import annotations

from collections.abc import Iterable

from IGBot.runtime.context import RuntimeContext
from IGBot.runtime.startup.contracts import StartupStage
from IGBot.runtime.startup.models import (
    StartupResult,
    StartupStageResult,
    StartupStageStatus,
)


class StartupPipeline:
    """Execute injected startup stages in registration order."""

    def __init__(self, stages: Iterable[StartupStage]) -> None:
        self._stages = tuple(stages)
        if not self._stages:
            raise ValueError("StartupPipeline requires at least one stage")

    @classmethod
    def with_initial_stages(
        cls,
        internet_checker: StartupStage,
        airplane_mode_controller: StartupStage,
        instagram_launcher: StartupStage,
        account_verifier: StartupStage,
        stages: Iterable[StartupStage] = (),
    ) -> StartupPipeline:
        """Fix the implemented startup stages in authoritative order."""
        return cls(
            (
                internet_checker,
                airplane_mode_controller,
                instagram_launcher,
                account_verifier,
                *stages,
            )
        )

    @property
    def stages(self) -> tuple[StartupStage, ...]:
        """Return the immutable ordered stage registration."""
        return self._stages

    def execute(self, context: RuntimeContext) -> StartupResult:
        """Execute stages sequentially and stop at the first failure."""
        results: list[StartupStageResult] = []
        for stage in self._stages:
            result = stage.execute(context)
            if not isinstance(result, StartupStageResult):
                raise TypeError("Startup stages must return StartupStageResult")
            results.append(result)
            if result.status is StartupStageStatus.FAILED:
                break
        return self._build_result(tuple(results))

    @staticmethod
    def _build_result(
        stage_results: tuple[StartupStageResult, ...],
    ) -> StartupResult:
        failed_result = next(
            (
                result
                for result in stage_results
                if result.status is StartupStageStatus.FAILED
            ),
            None,
        )
        return StartupResult(
            startup_completed=failed_result is None,
            internet_available=StartupPipeline._last_value(
                stage_results, "internet_available"
            ),
            account_verified=StartupPipeline._last_value(
                stage_results, "account_verified"
            ),
            new_followers_found=StartupPipeline._last_value(
                stage_results, "new_followers_found"
            )
            or 0,
            startup_failed=failed_result is not None,
            stage_results=stage_results,
            failure_reason=failed_result.detail if failed_result else None,
        )

    @staticmethod
    def _last_value(
        results: tuple[StartupStageResult, ...], field_name: str
    ) -> bool | int | None:
        return next(
            (
                value
                for result in reversed(results)
                if (value := getattr(result, field_name)) is not None
            ),
            None,
        )
