from __future__ import annotations
import abc

from .cache import PriceCache
from .types import Quote


class MarketDataProvider(abc.ABC):
    """Abstract market-data source. One background task writes `cache`;
    everything else reads it. Concrete implementations: SimulatorProvider,
    MassiveProvider."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self._tracked: set[str] = set()

    # ---- lifecycle (idempotent) ------------------------------------------

    @abc.abstractmethod
    async def start(self) -> None:
        """Schedule the background update loop. Returns immediately; non-blocking."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Cancel the loop and release resources."""

    # ---- tracked universe ------------------------------------------------

    def set_tracked(self, tickers: set[str]) -> None:
        """Set watchlist ∪ open positions. The loop fetches/simulates exactly
        these; entries no longer tracked are dropped from the cache. The ONLY
        mutator of the tracked set."""
        tickers = {t.upper() for t in tickers}
        stale = self._tracked - tickers
        self._tracked = tickers
        if stale:
            self.cache.drop(stale)

    @property
    def tracked(self) -> set[str]:
        return set(self._tracked)

    # ---- reads (cheap, synchronous, identical across providers) -----------

    def get_quote(self, ticker: str) -> Quote | None:
        return self.cache.get(ticker.upper())

    def get_all_quotes(self) -> dict[str, Quote]:
        return self.cache.all()

    # ---- validation ------------------------------------------------------

    @abc.abstractmethod
    async def is_supported(self, ticker: str) -> bool:
        """True iff `ticker` is in this provider's supported universe. Gates
        watchlist adds (manual and AI-initiated)."""

    # ---- introspection ---------------------------------------------------

    @property
    @abc.abstractmethod
    def source(self) -> str:
        """'simulator' or 'massive' — for /api/health and logging."""
