"""RAM-only exploration state for a Follow source session."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

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

    def __init__(
        self,
        *args,
        start_selector: Callable[[int], int] = random.randrange,
        source_label: str | None = None,
        source_path: str | Path | None = None,
    ):
        super().__init__(*args)
        total = len(self._sources)
        start = start_selector(total) if total else 0
        if total and not 0 <= start < total:
            raise ValueError("Source start selector returned an invalid index")
        positions = tuple(range(1, total + 1))
        self._sources = self._sources[start:] + self._sources[:start]
        self._configured_positions = positions[start:] + positions[:start]
        self._initial_source_pending = True
        self._source_origin_pending = True
        self._source_label = source_label
        self._source_path = Path(source_path) if source_path is not None else None

    def record_evaluated(self, context: RuntimeContext) -> None:
        self._discovery.session.evaluated += 1

    def _source_selected(self, context: RuntimeContext, source: str) -> None:
        total = len(self._sources)
        if self._source_origin_pending and self._source_path is not None:
            label = self._source_label or "discovery"
            loaded = ", ".join(self._sources)
            context.logger.info(
                f"[Source] Loaded {label} sources "
                f"(source={self._source_path}; loaded={loaded})"
            )
            self._source_origin_pending = False
        context.logger.info(f"[Source] Available configured sources: {total}")
        position = self._configured_positions[self._source_index]
        if self._initial_source_pending:
            context.logger.info(
                f"[Source] Random starting source: {source} ({position}/{total})"
            )
            self._initial_source_pending = False
        else:
            context.logger.info(
                f"[Source] Rotating to next source: {source} ({position}/{total})"
            )

    def next_candidate(self, context: RuntimeContext) -> CandidateResult:
        if self._sources and self._discovery.session.evaluated >= 50:
            context.logger.info(
                f"[Source] Source Session finished (evaluated_profiles={self._discovery.session.evaluated})"
            )
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
