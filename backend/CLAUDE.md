# FinAlly Backend

FastAPI + `uv` backend for the FinAlly trading workstation. This file orients
work inside `backend/`. The authoritative design is `../planning/PLAN.md` and
`../planning/MARKET_DATA_DESIGN.md` (plus the companion `MARKET_*` specs); read
those before changing behavior.

## Running and testing

Python **3.12+** is required (`pyproject.toml` pins `>=3.12`). The system PATH
here has Anaconda 3.8/3.9 first, which cannot even collect the suite (PEP 604
annotations). Always let `uv` provide the interpreter and the `dev` extras:

```
uv run --python 3.12 --extra dev pytest -q     # run from backend/
uv run --python 3.12 uvicorn app:app --port 8000
```

Tests live in `backend/tests/` (pytest, `asyncio_mode = "auto"`). `uv.lock` is
committed; keep it in sync with `uv lock` after changing dependencies.

A rich terminal demo of the simulator (`demo/market_demo.py`, behind the
optional `demo` extra) streams live prices with color flashes and sparklines:

```
uv run --python 3.12 --extra demo python -m demo.market_demo
uv run --python 3.12 --extra demo python -m demo.market_demo --seed 42 --duration 10
```

`rich` is imported lazily inside the rendering functions so the pure helpers
stay importable (and unit-tested) without the `demo` extra.

## Layout and imports

Flat module layout — imports are top-level (`from market.cache import ...`,
`import db`, `from api import stream`), **not** `backend.*`. There is no
`backend/__init__.py`; `pytest` adds `.` via `pythonpath = ["."]` and the app
must be launched from `backend/`.

```
market/    pure async market-data layer — NO FastAPI dependency
  types.py       Quote (frozen), Direction
  cache.py       PriceCache — the single source of truth for prices
  provider.py    MarketDataProvider ABC
  seed.py        UNIVERSE / SEED_PRICES / DEFAULT_WATCHLIST (simulator universe)
  simulator.py   SimulatorProvider (GBM, default)
  massive.py     MassiveProvider (Polygon.io REST, when MASSIVE_API_KEY set)
  factory.py     create_provider() — env-based selection
  sse.py         quote_to_sse()
api/         FastAPI only: deps.py, stream.py
tracking.py  recompute_tracked() — watchlist ∪ positions
app.py       lifespan wiring + app.state.{cache,provider}
db.py        STUB (see below)
```

Only `api/` and `app.py` import FastAPI; `market/` stays framework-free and
unit-testable without a web server. Keep it that way.

## Core invariants (do not break)

1. **One interface, two providers, no downstream branching.** Consumers talk to
   `MarketDataProvider` / `PriceCache` and never check which provider is live.
2. **The cache is the single price source with exactly one writer** (the active
   provider's background task). The market task never writes SQLite.
3. **Tracked universe = watchlist ∪ open positions.** `set_tracked` is the only
   mutator; `recompute_tracked(app)` re-derives it from the DB and is called on
   startup and after any watchlist/position change.
4. **`reference_price` is first-price-wins, never mutated** — enforced solely in
   `PriceCache.update`. Both providers get correct reference/direction for free.
5. **An empty tracked set streams nothing.** The whole-universe fallback applies
   only before the first `set_tracked` (guarded by `_tracked_initialized`); never
   resurrect the universe for a deliberately empty set.

## Provider notes

- **Simulator** (`SimulatorProvider`): GBM with market/sector/idiosyncratic
  factors. Internal price is full precision; the cache value is rounded to cents.
  Draw order is `sorted()` so a seeded `random.Random(seed)` is reproducible
  across processes (`PYTHONHASHSEED`) — inject one in tests. Rare 2-5% event
  shocks (`event_prob`) are idiosyncratic; disable them when testing the factor
  correlation structure.
- **Massive** (`MassiveProvider`): one batched snapshot per cycle (free-tier
  safe), `429` → exponential backoff capped at 60s, transient errors swallowed so
  the loop survives. `is_supported` fails closed and is memoised — but transient
  failures are **not** cached, so a blip can't block a valid ticker. Timestamps
  from the API are nanoseconds; normalize to seconds. The API key goes in the
  Authorization header and is never logged.

## SSE

`GET /api/stream/prices` reads `cache.all()` every ~500ms and emits one JSON
frame per ticker (`ticker, price, prev_price, reference_price, timestamp,
direction, change_pct`) plus a 30s heartbeat comment. The generator is infinite;
when testing the real handler, drive `response.body_iterator` with a one-shot
request — httpx `ASGITransport` blocks forever on an infinite stream.

## Current scope / stubs

`db.py` is a **stub**: `init_if_needed()` is a no-op, `watchlist_tickers()`
returns the default seed watchlist so the market layer streams the ten default
tickers, `position_tickers()` returns empty. The real SQLite layer and the
portfolio/watchlist/health routes (`PLAN.md` §7/§8) are a separate milestone —
implement them there, then replace this stub.

## Conventions

- Short functions/modules; latest idiomatic library use; no emojis.
- Reproduce a bug with a failing test, find the root cause with evidence, then
  fix; prove the fix with the test.
- Env vars: `MASSIVE_API_KEY` (set → live data, else simulator),
  `MASSIVE_POLL_SECONDS` (default 15, malformed tolerated).
