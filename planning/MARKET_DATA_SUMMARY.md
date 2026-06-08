# Market Data Subsystem — Consolidated Summary

This document consolidates the market-data design into a single reference and
folds in the lessons learned from the code review. It supersedes four detailed
specs, now in `archive/`:

- `MARKET_DATA_DESIGN.md` — integration blueprint
- `MARKET_INTERFACE.md` — the provider contract + types
- `MARKET_SIMULATOR.md` — the GBM simulator internals
- `MASSIVE_API.md` — the Massive (Polygon.io) REST reference
- `MARKET_DATA_REVIEW.md` — the review whose findings became section 11

The master project spec remains `PLAN.md`. The implementation lives in
`backend/market/`, `backend/api/`, `backend/tracking.py`, and `backend/app.py`;
see `backend/CLAUDE.md` for working conventions.

---

## 1. Architecture at a glance

One FastAPI process (single container, port 8000). Provider selection is by
environment variable at startup; nothing downstream branches on which provider
is live.

```
env MASSIVE_API_KEY ─▶ create_provider(cache)
                         │
                 MarketDataProvider (abstract)
                   • SimulatorProvider (default)
                   • MassiveProvider   (live)
                         │ one background task writes the cache
                         ▼
                    PriceCache (in-memory: latest / prev / reference)
              reads │           │ reads            │ reads
        SSE /api/stream/prices  /api/portfolio   /api/watchlist (is_supported)
                         │ EventSource, ~500ms
                         ▼  Browser
```

Three invariants drive every decision:

1. **One interface, two providers, zero downstream branching.**
2. **The cache is the single source of truth for prices** — exactly one writer
   (the active provider's background task); the market task never writes SQLite.
3. **The tracked universe is `watchlist ∪ open positions`** so a held-but-
   unwatched ticker keeps live P&L.

Package boundary: `market/` is pure async Python with **no FastAPI dependency**;
only `api/` and `app.py` import FastAPI. Keep it that way so the provider/cache
stay unit-testable without a web server.

---

## 2. Data types (`market/types.py`)

`Quote` is the provider-neutral price record — both the cache entry and the SSE
payload. Frozen/immutable; the cache replaces, never mutates.

| Field | Meaning |
|---|---|
| `ticker` | symbol (upper-case) |
| `price` | current price (USD) |
| `prev_price` | price immediately before `price` (drives flash + direction) |
| `reference_price` | first price seen this process ("session open"); stable for the life of the process |
| `timestamp` | Unix seconds of last update |

Derived: `direction` (`up`/`down`/`flat` vs `prev_price`), `change` and
`change_pct` (vs `reference_price`).

**Two distinct "change %" metrics — do not conflate:** the watchlist's change %
is vs `reference_price` (on `Quote`); the positions table's % change is vs
`avg_cost` (computed in the portfolio layer, not here).

---

## 3. The price cache (`market/cache.py`)

In-memory `dict[str, Quote]` behind a `threading.Lock` (so a thread-executor
poller and the asyncio loop can both touch it safely).

- `update(ticker, price, ts=None)` — sets `reference_price` on first sight; rolls
  `prev_price` forward thereafter. **This is the only place `reference_price` is
  assigned**, which guarantees the first-price-wins / never-mutated invariant.
- `get`, `all` (returns an independent shallow copy so SSE can serialize outside
  the lock), `known_tickers`, `drop(tickers)`.
- Keys are upper-cased; reads are case-insensitive.

---

## 4. The provider interface (`market/provider.py`)

```python
class MarketDataProvider(abc.ABC):
    async def start(self) -> None        # schedule the background loop (idempotent)
    async def stop(self) -> None         # cancel the loop, release resources
    def set_tracked(self, tickers) -> None   # the ONLY mutator of the tracked set
    @property def tracked(self) -> set[str]
    def get_quote(self, ticker) -> Quote | None
    def get_all_quotes(self) -> dict[str, Quote]
    async def is_supported(self, ticker) -> bool   # gates watchlist adds
    @property def source(self) -> str    # "simulator" | "massive"
```

Contract guarantees the rest of the app relies on:

- `set_tracked` is the only way the tracked universe changes; it upper-cases,
  drops now-stale tickers from the cache, and records that it has been called.
- Reads go through the cache → cheap, synchronous, identical across providers.
  Only `is_supported` and lifecycle are async.
- `reference_price`/`prev_price` semantics come for free via `cache.update`.

**Empty-vs-uninitialised:** the base tracks a `_tracked_initialized` flag.
Before the first `set_tracked`, a provider may fall back to its whole universe so
the first frames are populated; after it has been called, an **empty** tracked
set means stream nothing. Both providers must agree on this (see lesson 11.2).

---

## 5. Simulator (`market/simulator.py`, `market/seed.py`) — default

Used whenever `MASSIVE_API_KEY` is absent/empty. In-process asyncio task.

**Seed universe = supported universe.** `seed.py` defines `UNIVERSE` (a
`TickerSpec` per symbol: `seed_price`, `annual_drift` mu, `annual_vol` sigma,
`sector`), the ten default watchlist tickers plus extras to add. `is_supported`
is just membership in `UNIVERSE`. `DEFAULT_WATCHLIST` lists the ten defaults.

**GBM step** over `dt = tick_seconds / SECONDS_PER_YEAR` (continuous-time year so
the toy is always "alive"):

```
S(t+dt) = S(t) · exp((mu − ½σ²)·dt + σ·√dt·Z)
```

- Always positive; moves scale with price (realistic percentages); the −½σ²
  term keeps expected growth equal to mu.
- **Correlated factors:** `Z = √w_m·Z_market + √w_s·Z_sector + √(1−w_m−w_s)·Z_idio`.
  One market draw shared by all; one per sector; one idiosyncratic per ticker.
  The √ weights keep `Z` unit-variance so σ still means what it says. Defaults
  `w_m=0.4`, `w_s=0.3` → tech co-moves more tightly than tech-vs-finance.
- **Events:** with small per-tick probability (`event_prob≈0.001`), a one-off
  ±2-5% multiplicative shock for drama.
- **Precision:** internal price stays full precision; the cache value is rounded
  to cents (avoids rounding drift while keeping the wire clean).
- **Determinism:** inject `random.Random(seed)`. Draw order is `sorted` over
  sectors and over the tracked set, so a seeded run is reproducible across
  processes regardless of `PYTHONHASHSEED` (see lesson 11.1).
- `~500ms` tick to match the SSE cadence.

---

## 6. Massive provider (`market/massive.py`) — live

Used when `MASSIVE_API_KEY` is set. Raw async `httpx` against the Massive REST
API ("Massive" is this project's alias for Polygon.io; base
`https://api.massive.com`, Bearer header, finite 10s timeout, key never logged).

**Prices — one batched snapshot per cycle** (free-tier safe at ~4 req/min on the
default 15s poll):

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,...
```

Price fallback chain per ticker (first usable wins; treat 0/"0" as missing):
`lastTrade.p → min.c → day.c → prevDay.c`. Missing tickers are simply absent
from the response — tolerate `count < len(requested)` and keep last cache value.
Timestamps are mixed units: `updated`/`lastTrade.t` are **nanoseconds**, bar `t`
is **milliseconds** — normalize to seconds when writing the cache.

**Validation — `is_supported`:**

```
GET /v3/reference/tickers?ticker=SYMBOL&active=true&market=stocks&limit=1
```

Supported iff `results` is non-empty and `results[0].ticker` matches (case-
insensitive). Memoised for the process lifetime, but **only definitive answers
are cached**; a transient network/HTTP failure returns False without caching so a
later retry of a valid symbol can succeed (lesson 11.3).

**Operational rules:** batch, never per-ticker loop; finite timeout; `429` →
exponential backoff capped at 60s, then recover; swallow transient errors so the
loop survives and the cache keeps last-known values; log each error condition
once (not every cycle).

Rate-limit / freshness by plan: Free/Basic 5 req/min and 15-min delayed; Starter
100 req/min; Developer+ effectively unlimited and real-time. Poll interval is
config-driven (`MASSIVE_POLL_SECONDS`).

---

## 7. Selection & wiring (`market/factory.py`, `app.py`, `tracking.py`)

- `create_provider(cache)` → `MassiveProvider` if `MASSIVE_API_KEY` is set and
  non-empty, else `SimulatorProvider`. `MASSIVE_POLL_SECONDS` is parsed
  defensively (malformed → default 15).
- `app.py` lifespan: `db.init_if_needed()` → build cache + provider → store on
  `app.state` → `recompute_tracked(app)` → `provider.start()`; `provider.stop()`
  on shutdown.
- `tracking.recompute_tracked(app)` re-derives `watchlist ∪ positions` from the
  DB and calls `set_tracked`. A DB-derived recompute is idempotent and cannot
  desync; call it on startup and after every trade / watchlist mutation.
- `api/deps.py` exposes `get_cache` / `get_provider` reading `request.app.state`.

---

## 8. SSE streaming (`api/stream.py`, `market/sse.py`)

`GET /api/stream/prices` — long-lived `text/event-stream`; the browser uses
native `EventSource` (auto-reconnect). The endpoint reads `cache.all()` every
~500ms and emits one JSON frame per ticker; it does not call the provider
(provider→cache and cache→SSE are decoupled). A 30s heartbeat comment keeps
proxies from reaping idle connections; headers include `Cache-Control: no-cache`
and `X-Accel-Buffering: no`.

Frame fields: `ticker, price, prev_price, reference_price, timestamp, direction,
change_pct`.

**Cadence is independent of the provider.** SSE always emits every ~500ms; the
simulator updates the cache every ~500ms, Massive every ~15s (between polls SSE
re-emits the last values — the flash just doesn't change). Frontend logic is
identical for both. Connection dot maps from `EventSource.readyState`:
OPEN→green, CONNECTING→yellow, CLOSED→red.

---

## 9. How the rest of the app uses market data

| Consumer | Uses |
|---|---|
| SSE `/api/stream/prices` | `cache.all()` every ~500ms |
| Watchlist add `POST /api/watchlist` | `await provider.is_supported(t)` → 400 if false; then `recompute_tracked` |
| Watchlist remove `DELETE /api/watchlist/{t}` | delete row → `recompute_tracked` (held ticker stays cached via positions) |
| Trade `POST /api/portfolio/trade` | execute → `recompute_tracked` (newly held ticker starts streaming) |
| Portfolio `GET /api/portfolio` | `provider.get_quote(t).price` → unrealized P&L |
| Health `GET /api/health` | `provider.source` |
| AI chat | same `is_supported` + `recompute_tracked` path |

There is intentionally **no historical-price endpoint**: charts and sparklines
accumulate from the SSE stream since page load.

---

## 10. Configuration

| Env var | Default | Effect |
|---|---|---|
| `MASSIVE_API_KEY` | empty | set & non-empty → live Massive data; else simulator |
| `MASSIVE_POLL_SECONDS` | 15 | Massive poll interval; lower for paid tiers |

Non-env tunables (constructor args): simulator `tick_seconds` (0.5),
`w_market`/`w_sector` (0.4/0.3), `event_prob` (0.001); SSE interval (0.5),
heartbeat (30s).

---

## 11. Lessons learned (from the market-data review)

Durable takeaways from the review; the fixes are in the implementation.

1. **A seeded RNG is not reproducible if draw order depends on set iteration.**
   Drawing per-sector / per-ticker randoms while iterating a `set` makes the
   sequence depend on `PYTHONHASHSEED`, so "deterministic when seeded" held only
   within one process. Sort any iteration that drives RNG draws.

2. **Distinguish "never set" from "set to empty."** A truthiness fallback
   (`targets = self._tracked or whole_universe`) cannot tell them apart, so an
   empty watchlist resurrected the entire universe in the simulator while Massive
   streamed nothing. Use an explicit `_tracked_initialized` flag and make both
   providers agree: empty tracked → stream nothing.

3. **Fail closed, but do not memoise transient failures.** Caching a network/HTTP
   error from `is_supported` permanently blocks a valid symbol for the process
   lifetime. Cache only definitive answers (found / confirmed not-found); on
   exceptions return False without caching.

4. **Do not measure statistical properties on quantised values.** Per-tick moves
   are sub-cent, so the correlation test computed on cent-rounded cache prices
   was dominated by rounding noise. Measure on full-precision internal prices.
   Also: rare large event shocks dominate a short window's variance — disable
   events when asserting the factor-correlation structure.

5. **Never silently swallow loop exceptions.** Background loops must not crash,
   but they must log — once per condition (e.g. 401/403) rather than every cycle,
   so a bad key or outage is diagnosable without log spam.

6. **Beware truthiness on numeric fields.** `if v:` treats `0` and `"0"` as
   missing — sometimes intended (skip a zero price), sometimes a bug. Be explicit
   about None vs zero.

7. **Pin and use the right interpreter.** The suite requires Python 3.12; the
   default interpreter on the dev box was older and couldn't even collect the
   tests. Standardise on `uv run --python 3.12 --extra dev pytest` and add
   `from __future__ import annotations` consistently. Commit `uv.lock`.

8. **Test the real wiring, not a stand-in.** Earlier the SSE "integration" test
   reimplemented its own endpoint. Drive the real handler — but note its
   generator is infinite, so httpx `ASGITransport` blocks forever; invoke the
   handler directly and iterate `response.body_iterator` with a one-shot request.

9. **Cover the switches and seams.** Add tests for the factory (provider
   selection, poll parsing), `tracking` (the union recompute), `deps`, and a
   single parametrised conformance suite asserting both providers satisfy the
   contract and emit the same `Quote` shape.

---

## 12. Current scope

`db.py` is a stub: it returns the default seed watchlist so the market layer
streams the ten default tickers, with no positions. The real SQLite layer and
the portfolio / watchlist / health routes (`PLAN.md` §7/§8) are a separate
milestone; implement them there and replace the stub.
