# Market Data Backend — Detailed Design

> **Scope.** This is the **implementation blueprint** for FinAlly's entire
> market-data subsystem: the unified provider interface, the in-process GBM
> simulator, the Massive (Polygon.io) live client, the shared price cache, the
> SSE streaming endpoint, and the FastAPI wiring that binds them together.
>
> It is the build-from document for the Market Data agent. It **consolidates and
> operationalises** three companion specs and adds the connective tissue they
> leave open (the SSE endpoint, app lifespan/DI, the tracked-universe recompute
> helper, and config):
>
> - [`MARKET_INTERFACE.md`](./MARKET_INTERFACE.md) — the abstract contract + types
> - [`MARKET_SIMULATOR.md`](./MARKET_SIMULATOR.md) — the GBM simulator internals
> - [`MASSIVE_API.md`](./MASSIVE_API.md) — the Massive REST endpoints + parsing
>
> Where this doc and a companion spec overlap, they agree; where they differ in
> emphasis, the companion spec is authoritative for *its* component and this doc is
> authoritative for *integration*. Realises `PLAN.md` §6, §8, §10 and Design
> Decisions #1, #2, #3, #5, #7, #12, #13.

---

## 1. Design at a Glance

```
                         ┌──────────────────────────────────────────────┐
                         │  FastAPI process (single container, port 8000) │
                         │                                                │
  env: MASSIVE_API_KEY ─▶│  create_provider(cache)  ──┐                   │
                         │                            ▼                   │
                         │      ┌───────────────────────────────┐        │
   one background task   │      │ MarketDataProvider (abstract)  │        │
   writes the cache  ────┼────▶ │  • SimulatorProvider (default) │        │
                         │      │  • MassiveProvider   (live)    │        │
                         │      └───────────────┬───────────────┘        │
                         │                      │ cache.update(...)       │
                         │                      ▼                         │
                         │            ┌──────────────────┐                │
                         │            │   PriceCache     │  (in-memory)    │
                         │            │  latest/prev/ref │                 │
                         │            └────────┬─────────┘                │
                         │     reads           │            reads         │
                         │   ┌─────────────────┼──────────────────┐       │
                         │   ▼                 ▼                  ▼        │
                         │  SSE          /api/portfolio     /api/watchlist │
                         │  /api/stream/prices  (current px)  (is_supported)│
                         └──────────────────────────────────────────────┘
                                          │  EventSource (SSE, ~500ms)
                                          ▼
                                      Browser (frontend)
```

**Three invariants drive every design choice:**

1. **One interface, two providers, zero downstream branching.** Selection is by
   env var at startup; SSE/portfolio/watchlist never check which provider is live
   (`MARKET_INTERFACE.md` §1).
2. **The cache is the single source of truth for prices.** Exactly one writer (the
   active provider's background task); everyone else reads. The market task never
   writes SQLite (`PLAN.md` §7, "Concurrency").
3. **The tracked universe is `watchlist ∪ open positions`.** A held-but-unwatched
   ticker keeps live P&L (Decision #3). One helper recomputes it; handlers call
   that helper after any mutation.

---

## 2. Module Layout

```
backend/
├── market/
│   ├── __init__.py
│   ├── types.py        # Quote, Direction (§3)
│   ├── cache.py        # PriceCache (§4)
│   ├── provider.py     # MarketDataProvider ABC (§5)
│   ├── seed.py         # UNIVERSE / SEED_PRICES — simulator universe (§6)
│   ├── simulator.py    # SimulatorProvider — GBM (§6)
│   ├── massive.py      # MassiveProvider — REST (§7)
│   ├── factory.py      # create_provider() (§8)
│   └── sse.py          # quote_to_sse() + price event stream (§9)
├── api/
│   ├── stream.py       # GET /api/stream/prices (§9)
│   ├── watchlist.py    # uses is_supported + recompute_tracked (§10)
│   ├── portfolio.py    # reads cache for current price (§10)
│   └── health.py       # reports provider.source (§10)
├── tracking.py         # recompute_tracked() helper (§10.1)
└── app.py              # lifespan wiring + app.state (§8)
```

The `market/` package is self-contained and has **no dependency on FastAPI** — it
is pure async Python that could be reused in a CLI or worker. Only `api/` and
`app.py` import FastAPI. This keeps the provider/cache unit-testable without a web
server.

---

## 3. Data Types

The provider-neutral price record. This *is* the SSE payload and what the
watchlist/portfolio read. (Mirrors `MARKET_INTERFACE.md` §2 — reproduced here so
this doc is implementable standalone.)

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
    """Latest known price for one ticker. Stored in the cache, pushed over SSE.
    Prices are USD. Immutable — the cache replaces, never mutates."""
    ticker: str
    price: float            # current price
    prev_price: float       # the price immediately before `price` (flash + direction)
    reference_price: float  # first price seen this process ("session open"); stable for life of process
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

> **Two different "change %" metrics — do not conflate (Decision #7):**
>
> | Metric | Baseline | Computed where |
> |---|---|---|
> | Watchlist `change %` | session **reference_price** | here, on `Quote` |
> | Positions `% change` | position **avg_cost** | portfolio layer (not here) |
>
> `reference_price` is set on the *first* price seen and **never mutated** for the
> life of the process (Decision #1). The cache enforces this — see §4.

---

## 4. The Price Cache

A single in-memory store written only by the active provider, read by everyone.
Thread-safe so a thread-executor poller and the asyncio loop can both touch it.

```python
# backend/market/cache.py
import time
import threading
from typing import Iterable
from .types import Quote


class PriceCache:
    """In-memory latest/prev/reference price per ticker.

    Single writer (the active provider's background task); many readers (SSE,
    portfolio, watchlist). The lock makes it safe regardless of whether the
    writer runs on the event loop (simulator) or in a thread executor (a sync
    Massive client, if ever used)."""

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._lock = threading.Lock()

    def update(self, ticker: str, price: float, ts: float | None = None) -> Quote:
        """Record a new price. Sets reference_price on first sight; rolls
        prev_price forward thereafter. Returns the resulting Quote.

        This is the ONLY place reference_price is assigned, guaranteeing the
        'first price wins, never mutated' invariant (Decision #1)."""
        ticker = ticker.upper()
        ts = ts if ts is not None else time.time()
        with self._lock:
            existing = self._quotes.get(ticker)
            if existing is None:
                q = Quote(ticker, price, price, price, ts)   # first sight: all equal
            else:
                q = Quote(ticker, price, existing.price, existing.reference_price, ts)
            self._quotes[ticker] = q
            return q

    def get(self, ticker: str) -> Quote | None:
        with self._lock:
            return self._quotes.get(ticker.upper())

    def all(self) -> dict[str, Quote]:
        with self._lock:
            return dict(self._quotes)   # shallow copy → safe to iterate outside lock

    def known_tickers(self) -> set[str]:
        with self._lock:
            return set(self._quotes)

    def drop(self, tickers: Iterable[str]) -> None:
        """Remove cache entries no longer tracked (not watched and not held)."""
        with self._lock:
            for t in tickers:
                self._quotes.pop(t.upper(), None)
```

**Why a copy in `all()`?** SSE iterates the snapshot every ~500 ms. Returning a
shallow copy lets the writer keep updating without the reader holding the lock for
the duration of a serialize-and-send. `Quote` is frozen, so the copied references
are safe.

---

## 5. The Provider Interface

```python
# backend/market/provider.py
from __future__ import annotations
import abc
from .cache import PriceCache
from .types import Quote


class MarketDataProvider(abc.ABC):
    """Abstract market-data source. One background task writes `cache`;
    everything else reads it. Concrete: SimulatorProvider, MassiveProvider."""

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
        mutator of the tracked set. Safe to call any time."""
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
        watchlist adds (manual and AI). Simulator: seed set. Massive: REST
        lookup (Decision #5)."""

    # ---- introspection ---------------------------------------------------
    @property
    @abc.abstractmethod
    def source(self) -> str:
        """'simulator' or 'massive' — for /api/health and logging."""
```

**Contract guarantees the rest of the app relies on:**

- `set_tracked` is the *only* way the tracked universe changes. The app computes
  `watchlist ∪ positions` and calls it on startup and after every trade/watchlist
  edit (§10.1).
- Reads (`get_quote`, `get_all_quotes`) go through the cache → cheap, sync, and
  identical for both providers. Only `is_supported` and lifecycle are async.
- `reference_price`/`prev_price` semantics come *for free* via `cache.update`, so
  both providers behave identically without re-implementing them.

---

## 6. SimulatorProvider (default)

Used whenever `MASSIVE_API_KEY` is absent/empty. Full math rationale in
`MARKET_SIMULATOR.md`; the implementation below is the build target.

### 6.1 Seed universe (= the simulator's supported universe)

```python
# backend/market/seed.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSpec:
    seed_price: float
    annual_drift: float   # mu  — expected annual return (0.08 = +8%/yr)
    annual_vol: float     # sigma — annualized volatility (0.30 = 30%)
    sector: str           # correlation grouping


# Seed prices double as "session open" values AND the supported universe.
# Must include the 10 default watchlist tickers (PLAN.md §7) + margin to add.
UNIVERSE: dict[str, TickerSpec] = {
    "AAPL":  TickerSpec(190.0, 0.10, 0.28, "tech"),
    "GOOGL": TickerSpec(175.0, 0.09, 0.30, "tech"),
    "MSFT":  TickerSpec(420.0, 0.11, 0.26, "tech"),
    "AMZN":  TickerSpec(185.0, 0.10, 0.33, "tech"),
    "TSLA":  TickerSpec(250.0, 0.05, 0.55, "auto"),
    "NVDA":  TickerSpec(120.0, 0.18, 0.50, "tech"),
    "META":  TickerSpec(500.0, 0.12, 0.35, "tech"),
    "JPM":   TickerSpec(200.0, 0.06, 0.22, "finance"),
    "V":     TickerSpec(280.0, 0.08, 0.20, "finance"),
    "NFLX":  TickerSpec(630.0, 0.10, 0.38, "media"),
    # extras so users have symbols to add
    "AMD":   TickerSpec(160.0, 0.14, 0.48, "tech"),
    "INTC":  TickerSpec(35.0,  0.02, 0.34, "tech"),
    "DIS":   TickerSpec(100.0, 0.05, 0.30, "media"),
    "BAC":   TickerSpec(38.0,  0.05, 0.26, "finance"),
    "WMT":   TickerSpec(70.0,  0.07, 0.18, "retail"),
    "KO":    TickerSpec(62.0,  0.04, 0.15, "consumer"),
    "PYPL":  TickerSpec(65.0,  0.04, 0.40, "finance"),
    "F":     TickerSpec(12.0,  0.03, 0.35, "auto"),
}

SEED_PRICES: dict[str, float] = {t: s.seed_price for t, s in UNIVERSE.items()}
DEFAULT_WATCHLIST = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
                     "NVDA", "META", "JPM", "V", "NFLX"]  # PLAN.md §7 seed
```

### 6.2 The GBM step

Geometric Brownian Motion over a small step `dt`:

```
S(t+dt) = S(t) · exp( (mu − ½σ²)·dt + σ·√dt·Z )
```

with `dt = tick_seconds / SECONDS_PER_YEAR` (continuous-time year so the toy is
always "alive"). `Z` blends a market factor, a sector factor, and idiosyncratic
noise so the watchlist co-moves like a real tape:

```
Z = √w_m·Z_market + √w_s·Z_sector + √(1 − w_m − w_s)·Z_idio
```

The `√` weights keep `Z` unit-variance so `σ` still means what it says. See
`MARKET_SIMULATOR.md` §3–§5 for the full derivation and tuning cheatsheet.

### 6.3 Implementation

```python
# backend/market/simulator.py
from __future__ import annotations
import asyncio
import math
import random
import time

from .provider import MarketDataProvider
from .cache import PriceCache
from .seed import UNIVERSE, TickerSpec

SECONDS_PER_YEAR = 365 * 24 * 3600


class _TickerState:
    def __init__(self, spec: TickerSpec):
        self.spec = spec
        self.price = spec.seed_price   # full-precision internal price


class SimulatorProvider(MarketDataProvider):
    """In-process GBM simulator. Default provider (no MASSIVE_API_KEY)."""

    def __init__(
        self,
        cache: PriceCache,
        tick_seconds: float = 0.5,     # ≈ SSE cadence (PLAN.md §6)
        w_market: float = 0.4,
        w_sector: float = 0.3,
        event_prob: float = 0.001,     # ~1 shock / 16 min / ticker
        rng: random.Random | None = None,
    ):
        super().__init__(cache)
        self._tick = tick_seconds
        self._w_market = w_market
        self._w_sector = w_sector
        self._event_prob = event_prob
        self._rng = rng or random.Random()
        self._state = {t: _TickerState(s) for t, s in UNIVERSE.items()}
        self._task: asyncio.Task | None = None

    @property
    def source(self) -> str:
        return "simulator"

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

    async def _loop(self) -> None:
        while True:
            try:
                self._step()
            except Exception:
                pass   # never kill the loop
            await asyncio.sleep(self._tick)

    def _step(self) -> None:
        dt = self._tick / SECONDS_PER_YEAR
        sqrt_dt = math.sqrt(dt)
        now = time.time()

        z_market = self._rng.gauss(0.0, 1.0)
        sectors = {s.spec.sector for s in self._state.values()}
        z_sector = {sec: self._rng.gauss(0.0, 1.0) for sec in sectors}
        w_idio = 1.0 - self._w_market - self._w_sector

        # Simulate the tracked union; before set_tracked is first called, fall
        # back to the whole universe so the first SSE frames are populated.
        targets = self._tracked or set(self._state)

        for ticker in targets:
            st = self._state.get(ticker)
            if st is None:
                continue   # not in the simulator universe
            spec = st.spec
            z = (math.sqrt(self._w_market) * z_market
                 + math.sqrt(self._w_sector) * z_sector[spec.sector]
                 + math.sqrt(w_idio) * self._rng.gauss(0.0, 1.0))
            drift = (spec.annual_drift - 0.5 * spec.annual_vol ** 2) * dt
            diffusion = spec.annual_vol * sqrt_dt * z
            st.price *= math.exp(drift + diffusion)

            if self._rng.random() < self._event_prob:                 # drama
                shock = self._rng.uniform(0.02, 0.05) * self._rng.choice((-1, 1))
                st.price *= (1.0 + shock)

            self.cache.update(ticker, round(st.price, 2), now)        # cents on the wire

    async def is_supported(self, ticker: str) -> bool:
        return ticker.upper() in UNIVERSE
```

**Key points:** one asyncio task; internal price stays full-precision (cache value
rounded to cents to avoid rounding drift); `cache.update` gives correct
reference/direction for free; injecting `random.Random(42)` makes runs fully
reproducible for tests.

---

## 7. MassiveProvider (live)

Used when `MASSIVE_API_KEY` is set. One batched snapshot request per cycle
refreshes every tracked ticker — free-tier safe at ~4 req/min (`MASSIVE_API.md`
§3, §4.1). Raw `httpx` (fully async, explicit timeout + 429 backoff).

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
        self._poll = poll_seconds          # 15s free-tier safe; lower for paid keys
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {api_key}"},   # never log the key
            timeout=10.0,                                      # finite — never hang the loop
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
                backoff = self._poll                       # recovered
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    backoff = min(backoff * 2, 60.0)       # rate-limit backoff
            except Exception:
                pass                                        # network blip → keep last cache
            await asyncio.sleep(backoff)

    async def _poll_once(self) -> None:
        tickers = self.tracked
        if not tickers:
            return
        r = await self._client.get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"tickers": ",".join(sorted(tickers))},   # one batched call
        )
        r.raise_for_status()
        for snap in r.json().get("tickers", []):             # missing tickers simply absent
            price = self._extract_price(snap)
            if price is not None:
                ts = (snap.get("updated", 0) / 1e9) or None  # ns → seconds
                self.cache.update(snap["ticker"], price, ts)

    @staticmethod
    def _extract_price(snap: dict) -> float | None:
        """Price fallback chain (MASSIVE_API.md §4.1): lastTrade.p → min.c →
        day.c → prevDay.c. First non-null wins."""
        for obj_key, val_key in (("lastTrade", "p"), ("min", "c"),
                                 ("day", "c"), ("prevDay", "c")):
            obj = snap.get(obj_key) or {}
            v = obj.get(val_key)
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
            ok = False        # fail CLOSED — never admit an unvalidated symbol
        self._supported[t] = ok
        return ok
```

**Operational rules (`MASSIVE_API.md` §6):** batch never loop; finite timeout;
429 → exponential backoff capped at 60 s; swallow transient errors so the cache
keeps last-known values; memoise `is_supported` and fail closed. Timestamps are
mixed units — `updated`/`lastTrade.t` are **nanoseconds**, bar `t` is
**milliseconds**; normalise to seconds when writing the cache.

---

## 8. Provider Selection & App Wiring

### 8.1 Factory

```python
# backend/market/factory.py
import os
from .cache import PriceCache
from .provider import MarketDataProvider
from .massive import MassiveProvider
from .simulator import SimulatorProvider


def create_provider(cache: PriceCache) -> MarketDataProvider:
    """MASSIVE_API_KEY set & non-empty → MassiveProvider; else SimulatorProvider
    (PLAN.md §5)."""
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    poll = float(os.environ.get("MASSIVE_POLL_SECONDS", "15"))
    if key:
        return MassiveProvider(cache, api_key=key, poll_seconds=poll)
    return SimulatorProvider(cache)
```

### 8.2 Lifespan — single point of construction

```python
# backend/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .market.cache import PriceCache
from .market.factory import create_provider
from .tracking import recompute_tracked
from . import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_if_needed()                      # lazy schema + seed (PLAN.md §7)
    cache = PriceCache()
    provider = create_provider(cache)
    app.state.cache = cache
    app.state.provider = provider
    recompute_tracked(app)                   # watchlist ∪ positions (§10.1)
    await provider.start()
    try:
        yield
    finally:
        await provider.stop()


app = FastAPI(lifespan=lifespan)
# app.include_router(stream.router) ... etc.
```

### 8.3 Dependency access

```python
# backend/api/deps.py
from fastapi import Request
from ..market.provider import MarketDataProvider
from ..market.cache import PriceCache


def get_provider(request: Request) -> MarketDataProvider:
    return request.app.state.provider


def get_cache(request: Request) -> PriceCache:
    return request.app.state.cache
```

---

## 9. SSE Streaming — `GET /api/stream/prices`

The one streaming endpoint (`PLAN.md` §8). Long-lived; the browser uses native
`EventSource`, which handles reconnection. The server pushes one event per tracked
ticker every ~500 ms, reading the cache snapshot (it does **not** call the
provider directly — provider→cache and cache→SSE are decoupled).

### 9.1 Event payload

Each SSE `data:` line is one JSON object — exactly the fields `PLAN.md` §6
mandates:

```python
# backend/market/sse.py
import json
from .types import Quote


def quote_to_sse(q: Quote) -> str:
    """Serialize one Quote as an SSE 'message' event frame."""
    payload = {
        "ticker": q.ticker,
        "price": q.price,
        "prev_price": q.prev_price,
        "reference_price": q.reference_price,
        "timestamp": q.timestamp,
        "direction": q.direction.value,          # "up" | "down" | "flat"
        "change_pct": round(q.change_pct, 4),     # convenience for the watchlist
    }
    return f"data: {json.dumps(payload)}\n\n"
```

Example wire output for one frame:

```
data: {"ticker": "AAPL", "price": 190.42, "prev_price": 190.31, "reference_price": 190.0, "timestamp": 1699564799.5, "direction": "up", "change_pct": 0.2211}

```

### 9.2 The endpoint

```python
# backend/api/stream.py
import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..market.cache import PriceCache
from ..market.sse import quote_to_sse
from .deps import get_cache

router = APIRouter()

SSE_INTERVAL = 0.5      # ~500ms cadence (PLAN.md §6, §10)
HEARTBEAT_EVERY = 30.0  # comment ping to keep proxies from closing idle conns


async def _price_event_gen(request: Request, cache: PriceCache):
    # On connect, flush the current snapshot immediately so the client paints
    # without waiting a full interval.
    last_beat = 0.0
    first = True
    while True:
        if await request.is_disconnected():     # client closed the tab
            break
        for q in cache.all().values():
            yield quote_to_sse(q)
        # periodic heartbeat (SSE comment line) — ignored by EventSource,
        # but keeps intermediaries from reaping the idle connection.
        last_beat += SSE_INTERVAL
        if first or last_beat >= HEARTBEAT_EVERY:
            yield ": ping\n\n"
            last_beat = 0.0
            first = False
        await asyncio.sleep(SSE_INTERVAL)


@router.get("/api/stream/prices")
async def stream_prices(request: Request, cache: PriceCache = Depends(get_cache)):
    return StreamingResponse(
        _price_event_gen(request, cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",      # disable proxy buffering (nginx)
        },
    )
```

### 9.3 Cadence: SSE vs poll are independent

SSE always emits every ~500 ms regardless of provider. The simulator updates the
cache every ~500 ms (so prices change every frame); Massive updates it every ~15 s
(so between polls SSE simply re-emits the last cached values — the flash just
doesn't change). **The frontend logic is identical for both sources** — this is
intentional (`MARKET_INTERFACE.md` §8).

### 9.4 Frontend contract (informative)

```js
const es = new EventSource("/api/stream/prices");
es.onmessage = (e) => {
  const q = JSON.parse(e.data);   // {ticker, price, prev_price, reference_price, timestamp, direction, change_pct}
  applyTick(q);                   // flash by q.direction; sparkline.push(q.price)
};
// Connection dot from es.readyState: OPEN→green, CONNECTING→yellow, CLOSED→red (Decision #12)
```

`EventSource` auto-reconnects on drop; no client retry code needed (`PLAN.md`
§10). The connection-status dot maps directly off `readyState`.

---

## 10. How the Rest of the App Uses Market Data

| Consumer | Uses | Notes |
|---|---|---|
| **SSE** `/api/stream/prices` | `cache.all()` every ~500 ms | §9 |
| **Watchlist add** `POST /api/watchlist` | `await provider.is_supported(t)` → 400 if false; then `recompute_tracked` | gates manual + AI adds (§10.2) |
| **Watchlist remove** `DELETE /api/watchlist/{t}` | delete row → `recompute_tracked` | held ticker stays cached via positions (Decision #3) |
| **Trade** `POST /api/portfolio/trade` | execute → `recompute_tracked` | a newly held ticker starts streaming |
| **Portfolio** `GET /api/portfolio` | `provider.get_quote(t).price` | current price → unrealized P&L |
| **Health** `GET /api/health` | `provider.source` | "simulator" / "massive" |
| **AI chat** | same `is_supported` + `recompute_tracked` path | Decision #5 |

### 10.1 The tracked-universe recompute helper

The single chokepoint that keeps the cache/stream covering `watchlist ∪ positions`
(Decision #3). Every handler that mutates the watchlist or positions calls it.

```python
# backend/tracking.py
from fastapi import FastAPI
from . import db


def tracked_tickers() -> set[str]:
    """watchlist ∪ open positions — the universe the cache must cover."""
    return {t.upper() for t in db.watchlist_tickers()} \
         | {t.upper() for t in db.position_tickers()}


def recompute_tracked(app: FastAPI) -> None:
    """Re-derive the tracked set from the DB and push it to the provider.
    Call after startup and after every trade / watchlist mutation."""
    app.state.provider.set_tracked(tracked_tickers())
```

> **Why a DB-derived recompute rather than incremental add/remove?** It is
> idempotent and impossible to desync: whatever the DB says *is* the tracked set.
> A dropped ticker (removed from the watchlist **and** not held) is pruned from
> the cache by `set_tracked`; a held-but-unwatched ticker remains because
> `position_tickers()` still includes it.

### 10.2 Watchlist add (validation gate)

```python
# backend/api/watchlist.py (excerpt)
from fastapi import APIRouter, Depends, HTTPException, Request
from .deps import get_provider
from ..market.provider import MarketDataProvider
from ..tracking import recompute_tracked
from .. import db

router = APIRouter()


@router.post("/api/watchlist")
async def add_ticker(body: dict, request: Request,
                     provider: MarketDataProvider = Depends(get_provider)):
    ticker = body["ticker"].strip().upper()
    if not await provider.is_supported(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"{ticker} is not a supported ticker for the {provider.source} provider",
        )
    db.add_watchlist(ticker)              # UNIQUE(user_id, ticker) — idempotent
    recompute_tracked(request.app)        # provider starts streaming it
    return {"ticker": ticker, "added": True}
```

The identical `is_supported` + `recompute_tracked` path is reused by the AI chat's
`watchlist_changes` handling, so AI-initiated adds are validated the same way
(Decision #5).

### 10.3 Health

```python
# backend/api/health.py (excerpt)
@router.get("/api/health")
async def health(provider=Depends(get_provider)):
    return {"status": "ok", "market_source": provider.source}
```

---

## 11. Configuration

| Env var | Default | Effect |
|---|---|---|
| `MASSIVE_API_KEY` | *(empty)* | set & non-empty → Massive live data; else simulator (`PLAN.md` §5) |
| `MASSIVE_POLL_SECONDS` | `15` | Massive poll interval; lower for paid tiers (§7) |

Tunables that are **not** env-driven (constructor args, change in code if needed):
simulator `tick_seconds` (0.5), `w_market`/`w_sector` (0.4/0.3), `event_prob`
(0.001); SSE `SSE_INTERVAL` (0.5), `HEARTBEAT_EVERY` (30). See
`MARKET_SIMULATOR.md` §7 for the simulator tuning cheatsheet.

> Decision #2/§4.5: there is **no** historical-price endpoint. Charts and
> sparklines accumulate from the SSE stream since page load. Do not add an aggregates
> route to the market layer.

---

## 12. Build Order (suggested)

1. `types.py`, `cache.py` — pure, no deps. Unit-test the cache reference/prev
   invariants first.
2. `provider.py` — the ABC + `set_tracked`/`drop` wiring.
3. `seed.py` + `simulator.py` — get the default path live end to end.
4. `sse.py` + `api/stream.py` — verify a browser/`curl -N` sees frames.
5. `app.py` lifespan + `tracking.py` — wire startup and the recompute helper.
6. `api/watchlist.py`, `api/portfolio.py`, `api/health.py` integration.
7. `massive.py` — last; mock the REST in tests, no key needed for CI.

`curl` smoke test for the stream:

```bash
curl -N http://localhost:8000/api/stream/prices    # -N = no buffering; watch frames tick
```

---

## 13. Testing Plan (`PLAN.md` §12)

### 13.1 Cache & types (unit)

- First `update` sets `reference_price == prev_price == price`; later updates roll
  `prev_price` forward and **leave `reference_price` fixed** across many ticks
  (Decision #1).
- `direction` is up/down/flat per price vs prev; `change_pct` vs reference.
- `drop` removes only the named tickers; `all()` returns an independent copy.

### 13.2 Provider contract (parametrised over BOTH providers)

A single suite runs against `SimulatorProvider` and a `MassiveProvider` with a
mocked `httpx` client:

- `is_supported` accepts known-universe tickers, rejects unknown (`"ZZZZ"`).
  Simulator: seed set. Massive: mock `/v3/reference/tickers` returning the
  symbol / empty `results`.
- After `set_tracked({"AAPL"})` only AAPL is fetched/simulated; the cache covers
  exactly the tracked set; a ticker removed from tracking is dropped.
- **Union coverage (Decision #3):** with watchlist `{AAPL}` and a held position in
  `MSFT` (not watched), `tracked_tickers()` yields `{AAPL, MSFT}` and both stay
  cached after the watchlist drops MSFT-equivalent — i.e. a held-but-unwatched
  ticker keeps a cache entry.
- Both produce the same `Quote` shape.

### 13.3 Simulator specifics

- Every tick yields a finite, **strictly positive** price for every tracked
  ticker (GBM invariant).
- With `annual_vol=0` and a fixed `mu`, price grows deterministically by
  `exp(mu·dt)` per tick (volatility off ⇒ no randomness).
- Seeded `random.Random(42)` ⇒ a full tick sequence is reproducible.
- First emitted price == seed price == `reference_price`; later ticks change
  `price`/`prev_price` only.
- **Correlation (statistical, seeded):** over many ticks, same-sector return
  correlation > cross-sector correlation (loose threshold).

### 13.4 Massive specifics (mocked REST)

- `_extract_price` follows the fallback chain and tolerates missing
  `lastTrade`/null fields; returns `None` when no usable field exists.
- A snapshot response with `count < len(requested)` (a missing ticker) does not
  raise; present tickers update, absent ones keep their last cache value.
- `429` lengthens the backoff and the loop survives; a recovered cycle restores
  the base interval.
- `updated` nanoseconds normalise to seconds in the cached `Quote.timestamp`.
- `is_supported` is memoised (second call issues no HTTP) and **fails closed** on
  network error.

### 13.5 SSE / API (integration, `httpx.ASGITransport`)

- `GET /api/stream/prices` returns `text/event-stream`; the first read contains
  one `data:` frame per cached ticker with all required fields.
- `POST /api/watchlist` with an unknown symbol → 400 and the ticker is not added;
  with a supported symbol → 200 and a subsequent stream read includes it.
- Removing a *held* ticker from the watchlist: it still appears in the stream and
  `/api/portfolio` still prices it (Decision #3 end-to-end).
- `GET /api/health` reports the active `market_source`.

E2E coverage (Playwright, `LLM_MOCK=true`) for streaming/resilience lives in
`test/` per `PLAN.md` §12 (fresh start shows streaming prices; reject unknown
ticker; held-ticker keeps streaming; SSE disconnect→reconnect).

---

## 14. Traceability

| `PLAN.md` requirement / Decision | Realised by |
|---|---|
| §6 Two implementations, one interface | §5 ABC, §6 sim, §7 Massive, §8 factory |
| §6 Shared price cache (latest/prev/ref) | §4 `PriceCache`, §3 `Quote` |
| §6/§8 SSE stream of all tracked tickers | §9 endpoint |
| §6/§8 `is_supported` gates adds | §6.3, §7, §10.2 |
| §8 endpoints (stream/watchlist/portfolio/health) | §9, §10 |
| Decision #1 reference price first & immutable | §4 `cache.update` |
| Decision #2 no historical endpoint | §11 note |
| Decision #3 union of watchlist + positions | §10.1 `recompute_tracked` |
| Decision #5 provider-neutral validation | §6.3 seed / §7 REST |
| Decision #7 two distinct change-% metrics | §3 `Quote` table |
| Decision #12 connection dot from readyState | §9.4 |
| §7 market task never writes SQLite | §1 invariant 2, §6/§7 (cache only) |
