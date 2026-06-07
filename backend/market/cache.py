from __future__ import annotations
import time
import threading
from typing import Iterable

from .types import Quote


class PriceCache:
    """In-memory latest/prev/reference price per ticker.

    Single writer (the active provider's background task); many readers (SSE,
    portfolio, watchlist). Thread-safe so a thread-executor poller and the
    asyncio loop can share it without races."""

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._lock = threading.Lock()

    def update(self, ticker: str, price: float, ts: float | None = None) -> Quote:
        """Record a new price. Sets reference_price on first sight; rolls
        prev_price forward thereafter. Returns the resulting Quote.

        This is the ONLY place reference_price is assigned, guaranteeing the
        'first price wins, never mutated' invariant."""
        ticker = ticker.upper()
        ts = ts if ts is not None else time.time()
        with self._lock:
            existing = self._quotes.get(ticker)
            if existing is None:
                q = Quote(ticker, price, price, price, ts)  # first sight: all equal
            else:
                q = Quote(ticker, price, existing.price, existing.reference_price, ts)
            self._quotes[ticker] = q
            return q

    def get(self, ticker: str) -> Quote | None:
        with self._lock:
            return self._quotes.get(ticker.upper())

    def all(self) -> dict[str, Quote]:
        """Return a shallow copy safe to iterate outside the lock."""
        with self._lock:
            return dict(self._quotes)

    def known_tickers(self) -> set[str]:
        with self._lock:
            return set(self._quotes)

    def drop(self, tickers: Iterable[str]) -> None:
        """Remove cache entries no longer tracked (not watched and not held)."""
        with self._lock:
            for t in tickers:
                self._quotes.pop(t.upper(), None)
