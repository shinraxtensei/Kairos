"""Ports. Declared in the domain, implemented in infrastructure — never the reverse."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import Keyword, SourcePlatform


class TrendSourceError(RuntimeError):
    """An adapter failed to fetch. Adapters translate vendor errors into this.

    Vendor exception types must not escape the adapter — the application layer
    handles this one type and degrades (ENG-17).
    """


class TrendSource(ABC):
    """One external source of trend signals. See CONTEXT.md §5 before adding one."""

    @property
    @abstractmethod
    def platform(self) -> SourcePlatform: ...

    @property
    def is_critical(self) -> bool:
        """Whether a failure here should be treated as more than a degradation.

        Defaults to False on purpose: pytrends and TikTok Creative Center are
        unofficial and expected to break, so no source is critical unless it
        says so.
        """
        return False

    @abstractmethod
    def fetch(self, seeds: Sequence[Keyword]) -> Sequence[TrendSignal]:
        """Fetch current signals for the given seed keywords.

        Raises TrendSourceError on any vendor-side failure.
        """


class TrendSignalRepository(ABC):
    @abstractmethod
    def add_all(self, signals: Sequence[TrendSignal]) -> None: ...

    @abstractmethod
    def recent(
        self, *, platform: SourcePlatform | None = None, limit: int = 100
    ) -> Sequence[TrendSignal]: ...
