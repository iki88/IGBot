"""RAM-only exploration state for a Follow source session."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import product

from IGBot.runtime.candidates.models import CandidateResult, CandidateResultStatus
from IGBot.runtime.candidates.providers import FollowersProvider
from IGBot.runtime.context import RuntimeContext


@dataclass
class SourceSession:
    """One strategy and one letter cache for at most 50 evaluated profiles."""

    evaluated: int = 0
    letter_search: bool = False
    used_letters: set[str] = field(default_factory=set)
    failed_letters: set[str] = field(default_factory=set)

    def choose_strategy(self, followers: int | None) -> None:
        self.letter_search = followers is not None and followers >= 10_000

    def next_letter(
        self, first: str, second: str, choose: Callable = random.choice
    ) -> str | None:
        remaining = sorted(
            {a + b for a, b in product(first, second)} - self.used_letters
        )
        if not remaining:
            return None
        letter = choose(remaining)
        self.used_letters.add(letter)
        return letter


class FollowSourcesProvider(FollowersProvider):
    """Rotate source sessions without changing generic provider behavior."""

    def record_evaluated(self, context: RuntimeContext) -> None:
        self._discovery.session.evaluated += 1

    def _source_selected(self, context: RuntimeContext, source: str) -> None:
        total = len(self._sources)
        context.logger.info(f"[Source] Available configured sources: {total}")
        context.logger.info(
            f"[Source] Randomly selected: {source} ({self._source_index + 1}/{total})"
        )

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        if self._sources and self._discovery.session.evaluated >= 50:
            context.logger.info(
                f"[Source] Source Session finished (evaluated_profiles={self._discovery.session.evaluated})"
            )
            context.logger.info("[Source] Rotating to next source.")
            self._source_index = (self._source_index + 1) % len(self._sources)
            self._source_open = False
            self._discovery.session = SourceSession()
        return super().next_candidate(context)


class FollowProviderSequence:
    """Run configured discovery methods in order without merging their internals."""

    def __init__(self, providers: tuple[FollowSourcesProvider, ...]) -> None:
        if not providers:
            raise ValueError("Follow provider sequence requires at least one provider")
        self._providers = providers
        self._index = 0

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        while self._index < len(self._providers):
            result = self._providers[self._index].next_candidate(context)
            if (
                result.status is CandidateResultStatus.ALL_SOURCES_EXHAUSTED
                and self._index + 1 < len(self._providers)
            ):
                self._index += 1
                continue
            return result
        return CandidateResult(CandidateResultStatus.ALL_SOURCES_EXHAUSTED)

    def record_evaluated(self, context: RuntimeContext) -> None:
        self._providers[self._index].record_evaluated(context)
