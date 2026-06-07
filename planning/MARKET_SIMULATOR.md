# Market Simulator

> **Scope.** The design, math, and code structure for FinAlly's built-in price
> simulator — the **default** market-data source, used whenever `MASSIVE_API_KEY`
> is absent or empty (PLAN.md §5, §6). It implements the `SimulatorProvider` half
> of the [`MARKET_INTERFACE.md`](./MARKET_INTERFACE.md) contract: it writes the
> shared `PriceCache`; SSE and the portfolio layer read it, unaware the data is
> synthetic.

---

## 1. Goals

1. **Realistic-looking price action** with no external dependencies — runs as one
   in-process asyncio background task (PLAN.md §6).
2. **Geometric Brownian Motion (GBM)** with per-ticker drift and volatility, so
   prices stay positive and move with believable magnitude.
3. **Correlated sectors** — tech names move together, so the watchlist looks like
   a real market, not independent noise.
4. **Occasional drama** — random "events" produce sudden 2–5 % jumps for visual
   interest (PLAN.md §6).
5. **Fixed known universe** — the seed-price set *is* the simulator's supported
   universe; `is_supported` returns true only for these (PLAN.md §6, Decision #5).
6. **~500 ms tick** to match the SSE cadence (PLAN.md §6, §10).
7. **Deterministic when seeded** — accept an optional RNG seed so tests are
   reproducible.

---

## 2. Seed Universe

A fixed dict of realistic starting prices. This set defines both the simulator's
starting points **and** its supported universe. It must include the ten default
watchlist tickers (PLAN.md §7) plus a comfortable margin so users have symbols to
add.

```python
# backend/market/seed.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSpec:
    seed_price: float
    annual_drift: float        # mu  — expected annual return (e.g. 0.08 = +8%/yr)
    annual_vol: float          # sigma — annualized volatility (e.g. 0.30 = 30%)
    sector: str                # for correlation grouping


# Seed prices are illustrative "session open" values; tune to taste.
UNIVERSE: dict[str, TickerSpec] = {
    # --- the 10 default watchlist tickers (PLAN.md §7) ---
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
    # --- extra tickers so users can add beyond the defaults ---
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
```

> `is_supported(ticker)` is just `ticker.upper() in UNIVERSE`. Adding a ticker
> outside this set is rejected (PLAN.md §8) — both for manual and AI-initiated
> adds (Decision #5).

---

## 3. The GBM Math

Geometric Brownian Motion evolves a price `S` over a small time step `dt`:

```
S(t + dt) = S(t) · exp( (mu - 0.5·sigma²)·dt + sigma·sqrt(dt)·Z )
```

where `Z` is a standard normal draw. Working in **annualized** `mu`/`sigma`, the
time step for a 500 ms tick is a fraction of a trading year:

```
dt = tick_seconds / SECONDS_PER_TRADING_YEAR
```

We use a continuous-time year (`365 · 24 · 3600`) so prices drift even when the
real market is closed — this is a toy that should always look alive. Properties
that make GBM the right choice:

- **Always positive** — the `exp(...)` factor can never drive the price negative.
- **Returns, not levels** — the move scales with the current price, so a $600
  stock and a $12 stock both move by realistic *percentages*.
- **`-0.5·sigma²` drift correction** keeps the *expected* price growth equal to
  `mu` despite Jensen's inequality from the exponential.

---

## 4. Sector Correlation

Independent draws look like static. Real markets co-move, so each tick we blend a
**market factor**, a **sector factor**, and an **idiosyncratic** draw:

```
Z_ticker = sqrt(w_m)·Z_market + sqrt(w_s)·Z_sector + sqrt(1 - w_m - w_s)·Z_idio
```

- `Z_market` — one draw shared by **all** tickers this tick (broad risk-on/off).
- `Z_sector` — one draw shared within each sector (tech moves with tech).
- `Z_idio`   — a per-ticker draw (company-specific noise).

The `sqrt` weights keep `Z_ticker` unit-variance (a standard normal), so the GBM
volatility `sigma` still means what it says. Defaults: `w_m = 0.4`, `w_s = 0.3`
→ 30 % idiosyncratic. The result: when the market factor is positive, most of the
watchlist ticks green together; tech names correlate more tightly with each other
than with finance — exactly the "tech stocks move together" behaviour PLAN.md §6
calls for.

---

## 5. Random Events

Each tick, with small probability per ticker, inject a sudden shock on top of the
GBM step — the "occasional 2–5 % move for drama" (PLAN.md §6):

- Probability ≈ `0.001` per ticker per tick (~one event every ~16 min per ticker
  at 500 ms ticks; across ~18 tickers, several per hour overall).
- Magnitude: uniform in `±[2%, 5%]`, random sign.
- Applied as a one-off multiplicative bump (`price *= 1 + shock`) so it respects
  the always-positive invariant.

---

## 6. Code Structure

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
    """Mutable per-ticker simulation state."""
    def __init__(self, spec: TickerSpec):
        self.spec = spec
        self.price = spec.seed_price


class SimulatorProvider(MarketDataProvider):
    """In-process GBM price simulator. Default provider when no MASSIVE_API_KEY.
    Implements MarketDataProvider (see MARKET_INTERFACE.md)."""

    def __init__(
        self,
        cache: PriceCache,
        tick_seconds: float = 0.5,
        w_market: float = 0.4,
        w_sector: float = 0.3,
        event_prob: float = 0.001,
        rng: random.Random | None = None,
    ):
        super().__init__(cache)
        self._tick = tick_seconds
        self._w_market = w_market
        self._w_sector = w_sector
        self._event_prob = event_prob
        self._rng = rng or random.Random()
        self._state: dict[str, _TickerState] = {
            t: _TickerState(spec) for t, spec in UNIVERSE.items()
        }
        self._task: asyncio.Task | None = None

    @property
    def source(self) -> str:
        return "simulator"

    # ---- lifecycle -------------------------------------------------------
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
                pass  # never kill the loop
            await asyncio.sleep(self._tick)

    # ---- one simulation tick --------------------------------------------
    def _step(self) -> None:
        dt = self._tick / SECONDS_PER_YEAR
        sqrt_dt = math.sqrt(dt)
        now = time.time()

        # shared factors for this tick
        z_market = self._rng.gauss(0.0, 1.0)
        sectors = {s.spec.sector for s in self._state.values()}
        z_sector = {sec: self._rng.gauss(0.0, 1.0) for sec in sectors}
        w_idio = 1.0 - self._w_market - self._w_sector

        # only simulate/emit tickers that are tracked (watchlist ∪ positions),
        # but always keep at least the seed universe alive for snappy adds.
        targets = self._tracked or set(self._state)

        for ticker in targets:
            st = self._state.get(ticker)
            if st is None:
                continue  # not in the simulator universe; ignore
            spec = st.spec

            z = (
                math.sqrt(self._w_market) * z_market
                + math.sqrt(self._w_sector) * z_sector[spec.sector]
                + math.sqrt(w_idio) * self._rng.gauss(0.0, 1.0)
            )
            drift = (spec.annual_drift - 0.5 * spec.annual_vol ** 2) * dt
            diffusion = spec.annual_vol * sqrt_dt * z
            st.price *= math.exp(drift + diffusion)

            # occasional dramatic event
            if self._rng.random() < self._event_prob:
                shock = self._rng.uniform(0.02, 0.05) * self._rng.choice((-1, 1))
                st.price *= (1.0 + shock)

            self.cache.update(ticker, round(st.price, 2), now)

    # ---- validation ------------------------------------------------------
    async def is_supported(self, ticker: str) -> bool:
        return ticker.upper() in UNIVERSE
```

### Notes on the structure

- **One asyncio task**, `_loop`, ticks every `tick_seconds` and calls `_step`.
  No threads needed — the work per tick is trivial.
- **`_step` writes the cache via `cache.update`**, which sets `reference_price` on
  first sight and rolls `prev_price` forward (MARKET_INTERFACE.md §3). The
  simulator therefore gets correct reference/direction semantics for free.
- **Tracked set drives what's emitted.** It simulates the union of watchlist +
  positions (`self._tracked`), falling back to the whole universe before
  `set_tracked` is first called, so the very first SSE frames are populated.
- **Internal price kept full-precision**, cache value rounded to cents — avoids
  drift accumulation from rounding while keeping displayed prices clean.
- **`rng` injection** makes the whole simulation reproducible for tests: pass
  `random.Random(42)` and assert exact sequences.

---

## 7. Behaviour Tuning Cheatsheet

| Want | Change |
|---|---|
| Faster/slower flashing | `tick_seconds` (default 0.5 — keep ≈ SSE cadence) |
| Calmer / wilder market | per-ticker `annual_vol` in `UNIVERSE` |
| Stronger sector herding | raise `w_sector` (keep `w_market + w_sector < 1`) |
| More/less broad co-movement | `w_market` |
| More/less drama | `event_prob`, and the `(0.02, 0.05)` shock range |
| Reproducible test runs | pass a seeded `random.Random(...)` |

---

## 8. Testing (PLAN.md §12)

- **Valid prices:** every tick yields a finite, **strictly positive** price (GBM
  invariant) for every tracked ticker.
- **GBM correctness:** with `annual_vol=0` and a fixed `mu`, price grows
  deterministically by `exp(mu·dt)` per tick (volatility off → no randomness);
  with a seeded RNG, a full tick sequence is reproducible.
- **Reference price:** the first emitted price equals the seed price and becomes
  the immutable `reference_price`; later ticks change `price`/`prev_price` only.
- **`is_supported`:** true for every key in `UNIVERSE`, false for an unknown
  symbol (e.g. `"ZZZZ"`).
- **Tracked union:** after `set_tracked({"AAPL"})` only AAPL updates; a ticker
  removed from tracking is dropped from the cache (held-but-unwatched handling is
  exercised at the provider level via `set_tracked(watchlist ∪ positions)`).
- **Correlation (statistical):** over many ticks, same-sector return correlation
  exceeds cross-sector correlation (loose threshold; seeded RNG for stability).
- **Conformance:** runs against the shared `MarketDataProvider` contract suite
  alongside `MassiveProvider` (MARKET_INTERFACE.md §9).
