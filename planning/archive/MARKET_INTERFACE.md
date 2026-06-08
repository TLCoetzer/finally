# Market Data Interface

> **Scope.** Defines the single Python abstraction FinAlly uses to retrieve stock
> prices, with two interchangeable implementations selected at runtime:
>
> - **`MassiveProvider`** — live data from the Massive REST API, used when
>   `MASSIVE_API_KEY` is set and non-empty (see [`MASSIVE_API.md`](./MASSIVE_API.md)).
> - **`SimulatorProvider`** — in-process geometric-Brownian-motion price
>   simulator, used otherwise (see [`MARKET_SIMULATOR.md`](./MARKET_SIMULATOR.md)).
>
> All downstream code (SSE streaming, portfolio math, watchlist validation,
> frontend) talks **only** to this interface and is agnostic to the source. This
> realises PLAN.md §6 ("Two Implementations, One Interface") and Design Decisions
> #3, #5.

---

## 1. Design Goals

1. **One interface, two providers.** Selection is by env var; no downstream `if`.
2. **A single shared price cache** holds the latest, previous, and per-ticker
   reference price + timestamp. SSE reads from this cache; nothing else touches
   provider internals (PLAN.md §6, "Shared Price Cache").
3. **Track the union of watchlist and open positions** so a held-but-unwatched
   ticker keeps live P&L (Decision #3).
4. **Provider-neutral symbol validation** via `is_supported(ticker)` (Decision #5).
5. **Async-first.** A single background task per provider writes the cache; the
   market task never writes SQLite (PLAN.md §7, "Concurrency").
6. **Cheap to test.** The simulator needs no network; both providers conform to
   the same interface so unit tests assert against the contract.

---

## 2. Data Types

A provider-neutral price record. This is exactly the payload an SSE event carries
(PLAN.md §6, "SSE Streaming") plus what the watchlist/portfolio read.

```python
# backend/market/types.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


@dataclass(frozen=True)
class Quote:
    """The latest known price for one ticker, as stored in the cache and
    pushed over SSE. Prices are in USD."""
    ticker: str
    price: float            # current price
    prev_price: float       # price immediately before `price` (for flash + direction)
    reference_price: float  # first price seen this process (session "open"); stable for the process
    timestamp: float        # Unix seconds of last update

    @property
    def direction(self) -> Direction:
        if self.price > self.prev_price:
            return Direction.UP
        if self.price < self.prev_price:
            return Direction.DOWN
        return Direction.FLAT

    @property
    def change(self) -> float:
        """Absolute change vs session reference price."""
        return self.price - self.reference_price

    @property
    def change_pct(self) -> float:
        """Watchlist 'change %' = vs session reference price (Decision #7)."""
        if self.reference_price == 0:
            return 0.0
        return (self.price - self.reference_price) / self.reference_price * 100.0
```

> **Reference price semantics (PLAN.md §6, Decision #1).** `reference_price` is the
> *first* price observed for a ticker after process start and is **never mutated**
> for the life of the process. It is the baseline for the watchlist's change %.
> This is distinct from the positions table's % change, which is vs `avg_cost`
> (Decision #7) and is computed in the portfolio layer, not here.

---

## 3. The Price Cache

A single in-memory store, shared by the active provider and the SSE layer. It is
the only thing SSE reads from.

```python
# backend/market/cache.py
import time
import threading
from typing import Iterable
from .types import Quote


class PriceCache:
    """In-memory latest/prev/reference price per ticker.

    Written only by the active provider's background task; read by SSE and the
    portfolio/watchlist layers. Thread-safe so a thread-executor poller and the
    asyncio loop can share it.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._lock = threading.Lock()

    def update(self, ticker: str, price: float, ts: float | None = None) -> Quote:
        """Record a new price. Sets reference_price on first sight; rolls
        prev_price forward thereafter. Returns the resulting Quote."""
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
            return self._quotes.get(ticker)

    def all(self) -> dict[str, Quote]:
        with self._lock:
            return dict(self._quotes)

    def known_tickers(self) -> set[str]:
        with self._lock:
            return set(self._quotes)

    def drop(self, tickers: Iterable[str]) -> None:
        """Remove cache entries no longer tracked (not watched and not held)."""
        with self._lock:
            for t in tickers:
                self._quotes.pop(t, None)
```

---

## 4. The Provider Interface

```python
# backend/market/provider.py
from __future__ import annotations
import abc
from .cache import PriceCache
from .types import Quote


class MarketDataProvider(abc.ABC):
    """Abstract market-data source. One background task writes `cache`;
    everything else reads the cache. Implementations: MassiveProvider,
    SimulatorProvider."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self._tracked: set[str] = set()

    # ---- lifecycle -------------------------------------------------------
    @abc.abstractmethod
    async def start(self) -> None:
        """Begin the background update loop (idempotent). Returns once the
        loop is scheduled; does not block."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the background loop and release resources (idempotent)."""

    # ---- tracked universe ------------------------------------------------
    def set_tracked(self, tickers: set[str]) -> None:
        """Set the union of (watchlist ∪ open positions). The loop will fetch/
        simulate exactly these symbols; entries no longer tracked are dropped
        from the cache. Safe to call any time (e.g. after a trade or watchlist
        edit)."""
        tickers = {t.upper() for t in tickers}
        stale = self._tracked - tickers
        self._tracked = tickers
        if stale:
            self.cache.drop(stale)

    @property
    def tracked(self) -> set[str]:
        return set(self._tracked)

    # ---- reads (convenience pass-throughs to the cache) ------------------
    def get_quote(self, ticker: str) -> Quote | None:
        return self.cache.get(ticker.upper())

    def get_all_quotes(self) -> dict[str, Quote]:
        return self.cache.all()

    # ---- validation ------------------------------------------------------
    @abc.abstractmethod
    async def is_supported(self, ticker: str) -> bool:
        """True iff `ticker` is in this provider's supported universe. Gates
        watchlist adds (manual and AI-initiated). Simulator: seed-price set.
        Massive: provider symbol lookup (PLAN.md §6, Decision #5)."""

    # ---- introspection ---------------------------------------------------
    @property
    @abc.abstractmethod
    def source(self) -> str:
        """'massive' or 'simulator' — for /api/health and logging."""
```

### Contract notes

- **`set_tracked` is the only mutator of the tracked universe.** The app computes
  `watchlist ∪ positions` and calls it on startup and after any trade or
  watchlist change. The provider loop reads `self._tracked` each cycle.
- **Reads go through the cache**, so they are cheap, synchronous, and identical
  across providers. `is_supported` and lifecycle are the only async methods.
- **First-price → reference price** is handled by `PriceCache.update`, so both
  providers get correct reference semantics for free.

---

## 5. Provider Selection (Factory)

```python
# backend/market/factory.py
import os
from .cache import PriceCache
from .provider import MarketDataProvider
from .massive import MassiveProvider
from .simulator import SimulatorProvider


def create_provider(cache: PriceCache) -> MarketDataProvider:
    """Pick the provider from the environment (PLAN.md §5).

    MASSIVE_API_KEY set & non-empty  -> MassiveProvider (live data)
    otherwise                        -> SimulatorProvider (default)
    """
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if key:
        return MassiveProvider(cache, api_key=key)
    return SimulatorProvider(cache)
```

Wired once at app startup:

```python
# backend/app.py (sketch)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .market.cache import PriceCache
from .market.factory import create_provider
from . import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_if_needed()                      # lazy schema + seed (PLAN.md §7)
    cache = PriceCache()
    provider = create_provider(cache)
    provider.set_tracked(db.tracked_tickers())   # watchlist ∪ positions
    await provider.start()
    app.state.cache = cache
    app.state.provider = provider
    try:
        yield
    finally:
        await provider.stop()


app = FastAPI(lifespan=lifespan)
```

Whenever the watchlist or positions change, handlers recompute and call
`provider.set_tracked(db.tracked_tickers())` so the cache/stream cover the union
(Decision #3).

---

## 6. MassiveProvider (live)

Implements the interface over the REST endpoints in `MASSIVE_API.md`. One batched
snapshot request per cycle refreshes every tracked ticker.

```python
# backend/market/massive.py
import asyncio
import httpx
from .provider import MarketDataProvider
from .cache import PriceCache

BASE = "https://api.massive.com"


class MassiveProvider(MarketDataProvider):
    def __init__(self, cache: PriceCache, api_key: str, poll_seconds: float = 15.0):
        super().__init__(cache)
        self._api_key = api_key
        self._poll = poll_seconds            # 15s = free-tier safe (§3 of MASSIVE_API.md)
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        self._supported: dict[str, bool] = {}   # memoised is_supported answers

    @property
    def source(self) -> str:
        return "massive"

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._client.aclose()

    async def _loop(self) -> None:
        backoff = self._poll
        while True:
            try:
                await self._poll_once()
                backoff = self._poll                      # recovered
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    backoff = min(backoff * 2, 60.0)      # rate-limit backoff
            except Exception:
                pass                                       # never kill the loop
            await asyncio.sleep(backoff)

    async def _poll_once(self) -> None:
        tickers = self.tracked
        if not tickers:
            return
        r = await self._client.get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"tickers": ",".join(sorted(tickers))},
        )
        r.raise_for_status()
        for snap in r.json().get("tickers", []):
            price = self._extract_price(snap)
            if price is not None:
                # `updated` is nanoseconds; convert to seconds
                ts = snap.get("updated", 0) / 1e9 or None
                self.cache.update(snap["ticker"], price, ts)

    @staticmethod
    def _extract_price(snap: dict) -> float | None:
        """Price fallback chain (MASSIVE_API.md §4.1)."""
        for path in (("lastTrade", "p"), ("min", "c"), ("day", "c"), ("prevDay", "c")):
            obj = snap.get(path[0]) or {}
            v = obj.get(path[1])
            if v:
                return float(v)
        return None

    async def is_supported(self, ticker: str) -> bool:
        t = ticker.upper()
        if t in self._supported:
            return self._supported[t]
        try:
            r = await self._client.get(
                "/v3/reference/tickers",
                params={"ticker": t, "active": "true", "market": "stocks", "limit": 1},
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            ok = bool(results) and results[0].get("ticker", "").upper() == t
        except Exception:
            ok = False        # fail closed: don't add what we can't validate
        self._supported[t] = ok
        return ok
```

**Notes**

- Single batched request per cycle (never per-ticker) → free-tier safe.
- `429` triggers exponential backoff capped at 60 s; other errors are swallowed so
  the loop survives. The cache keeps last-known values across a failed cycle.
- `is_supported` is memoised for the process lifetime (the universe rarely changes)
  and **fails closed** so a network blip can't admit a bad symbol.

---

## 7. SimulatorProvider (default)

Full design and math in [`MARKET_SIMULATOR.md`](./MARKET_SIMULATOR.md). Interface
shape only here:

```python
# backend/market/simulator.py (interface surface; see MARKET_SIMULATOR.md for internals)
import asyncio
from .provider import MarketDataProvider
from .cache import PriceCache
from .seed import SEED_PRICES        # {"AAPL": 190.0, "GOOGL": 175.0, ...}


class SimulatorProvider(MarketDataProvider):
    def __init__(self, cache: PriceCache, tick_seconds: float = 0.5):
        super().__init__(cache)
        self._tick = tick_seconds      # ~500ms (PLAN.md §6)
        self._task: asyncio.Task | None = None
        # ... GBM state per ticker ...

    @property
    def source(self) -> str:
        return "simulator"

    async def start(self) -> None: ...   # spawn the GBM tick loop
    async def stop(self) -> None: ...

    async def is_supported(self, ticker: str) -> bool:
        # Simulator universe = the seed-price set (PLAN.md §6, Decision #5)
        return ticker.upper() in SEED_PRICES
```

**Universe difference (Decision #5):**

| Provider | `is_supported` returns true for |
|---|---|
| `SimulatorProvider` | only tickers in `SEED_PRICES` (the seed-price set) |
| `MassiveProvider` | any symbol the provider recognises (REST lookup) |

So in simulator mode the watchlist is limited to the seed universe; in Massive
mode it is not.

---

## 8. How the Rest of the App Uses This

| Consumer | Uses |
|---|---|
| **SSE** `GET /api/stream/prices` | `provider.get_all_quotes()` every ~500 ms; emits one event per quote (`ticker, price, prev_price, reference_price, timestamp, direction`) |
| **Watchlist add** `POST /api/watchlist` | `await provider.is_supported(ticker)` → reject if false; then `set_tracked(...)` |
| **Trade** `POST /api/portfolio/trade` | after execution, recompute and `set_tracked(watchlist ∪ positions)` so a newly held ticker streams |
| **Portfolio** `GET /api/portfolio` | `get_quote(ticker).price` for current price / unrealized P&L |
| **Health** `GET /api/health` | reports `provider.source` |
| **AI chat** | watchlist changes route through the same `is_supported` + `set_tracked` path (Decision #5) |

> **SSE cadence vs poll cadence are independent.** SSE pushes every ~500 ms
> regardless of provider; the simulator updates the cache every ~500 ms, while the
> Massive poller updates it every ~15 s. Between Massive polls, SSE simply
> re-emits the last cached values — the frontend flash just won't change. This is
> expected and keeps the client logic identical for both sources.

---

## 9. Testing the Contract (PLAN.md §12)

Both providers must satisfy these, asserted in `backend/` unit tests:

- `is_supported` accepts known-universe tickers and rejects unknown ones
  (simulator: seed set; Massive: mock the REST lookup).
- First observed price becomes `reference_price` and stays stable across many
  updates.
- The cache covers `watchlist ∪ positions`: a held ticker removed from the
  watchlist still has a cache entry (drive via `set_tracked`).
- `MassiveProvider._extract_price` follows the documented fallback chain and
  tolerates missing tickers / null `lastTrade`.
- Both providers conform to `MarketDataProvider` (same methods, same `Quote`
  output shape) — a single parametrised test suite can run against both.
