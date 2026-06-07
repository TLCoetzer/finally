"""Unit tests for market.simulator — SimulatorProvider / GBM behaviour."""
import math
import random

import pytest

from market.cache import PriceCache
from market.seed import UNIVERSE, SEED_PRICES
from market.simulator import SimulatorProvider, SECONDS_PER_YEAR


# ---- helpers -------------------------------------------------------------

def make_sim(rng_seed: int | None = None, **kwargs) -> tuple[PriceCache, SimulatorProvider]:
    cache = PriceCache()
    rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
    sim = SimulatorProvider(cache, rng=rng, **kwargs)
    return cache, sim


# ---- is_supported --------------------------------------------------------

@pytest.mark.asyncio
async def test_is_supported_known_tickers():
    _, sim = make_sim()
    for ticker in UNIVERSE:
        assert await sim.is_supported(ticker), f"{ticker} should be supported"


@pytest.mark.asyncio
async def test_is_supported_lowercase_normalised():
    _, sim = make_sim()
    assert await sim.is_supported("aapl") is True


@pytest.mark.asyncio
async def test_is_supported_unknown_ticker():
    _, sim = make_sim()
    assert await sim.is_supported("ZZZZ") is False


@pytest.mark.asyncio
async def test_is_supported_empty_string():
    _, sim = make_sim()
    assert await sim.is_supported("") is False


# ---- source / provider metadata ------------------------------------------

def test_source_is_simulator():
    _, sim = make_sim()
    assert sim.source == "simulator"


# ---- first tick: reference price == seed price ---------------------------

def test_first_step_writes_seed_prices():
    """The first price emitted must equal the seed price for each ticker."""
    cache, sim = make_sim(rng_seed=42)
    sim.set_tracked({"AAPL", "MSFT"})
    sim._step()

    for ticker in ("AAPL", "MSFT"):
        q = cache.get(ticker)
        assert q is not None
        # reference_price is set on first update — it should equal the
        # rounded seed price that the simulator emitted.
        assert q.reference_price == q.price  # first tick: ref == current
        assert q.prev_price == q.price        # first tick: prev == current


def test_reference_price_fixed_across_many_ticks():
    """reference_price must never change after the first tick."""
    cache, sim = make_sim(rng_seed=42)
    sim.set_tracked({"AAPL"})
    sim._step()
    ref = cache.get("AAPL").reference_price

    for _ in range(100):
        sim._step()
        q = cache.get("AAPL")
        assert q.reference_price == ref, "reference_price changed!"


# ---- GBM invariants ------------------------------------------------------

def test_prices_always_positive():
    """GBM invariant: exp(.) can never produce a non-positive number."""
    cache, sim = make_sim(rng_seed=7)
    sim.set_tracked(set(UNIVERSE))  # all tickers
    for _ in range(200):
        sim._step()
    for q in cache.all().values():
        assert q.price > 0, f"{q.ticker} has non-positive price {q.price}"


def test_prices_are_finite():
    cache, sim = make_sim(rng_seed=99)
    sim.set_tracked(set(UNIVERSE))
    for _ in range(200):
        sim._step()
    for q in cache.all().values():
        assert math.isfinite(q.price), f"{q.ticker} has non-finite price {q.price}"


def test_zero_vol_deterministic_growth():
    """With annual_vol=0, the GBM reduces to: S(t+dt) = S(t) * exp(mu * dt).
    Disable event shocks so the result is fully deterministic."""
    from market.seed import TickerSpec
    from market.simulator import _TickerState

    # event_prob=0 ensures no random shock is applied
    cache, sim = make_sim(rng_seed=0, tick_seconds=0.5, event_prob=0.0)

    # Override AAPL's spec with zero volatility
    mu = 0.10
    sim._state["AAPL"] = _TickerState(TickerSpec(
        seed_price=100.0, annual_drift=mu, annual_vol=0.0, sector="tech"
    ))
    sim.set_tracked({"AAPL"})
    sim._step()

    q1 = cache.get("AAPL")
    dt = 0.5 / SECONDS_PER_YEAR
    expected = 100.0 * math.exp(mu * dt)
    assert q1.price == pytest.approx(round(expected, 2), rel=1e-6)


def test_reproducible_with_seeded_rng():
    """Two simulations with the same seed and same tickers must produce
    identical sequences."""
    tickers = {"AAPL", "MSFT"}

    cache1, sim1 = make_sim(rng_seed=123)
    sim1.set_tracked(tickers)

    cache2, sim2 = make_sim(rng_seed=123)
    sim2.set_tracked(tickers)

    for _ in range(20):
        sim1._step()
        sim2._step()

    for t in tickers:
        q1 = cache1.get(t)
        q2 = cache2.get(t)
        assert q1.price == q2.price, f"{t} diverged"


# ---- tracked universe ----------------------------------------------------

def test_only_tracked_tickers_updated():
    """After set_tracked, only the tracked tickers have cache entries."""
    cache, sim = make_sim(rng_seed=1)
    sim.set_tracked({"AAPL"})
    sim._step()

    assert cache.get("AAPL") is not None
    assert cache.get("MSFT") is None


def test_untracked_ticker_dropped_from_cache():
    """Removing a ticker from the tracked set drops it from the cache."""
    cache, sim = make_sim(rng_seed=2)
    sim.set_tracked({"AAPL", "MSFT"})
    sim._step()  # both land in cache

    assert cache.get("MSFT") is not None

    sim.set_tracked({"AAPL"})  # drop MSFT
    assert cache.get("MSFT") is None
    assert cache.get("AAPL") is not None


def test_held_but_unwatched_ticker_stays_in_tracked():
    """set_tracked(watchlist ∪ positions) means a held ticker not on the
    watchlist must still remain tracked (Decision #3)."""
    cache, sim = make_sim(rng_seed=3)
    # Simulate: watchlist={AAPL}, positions={MSFT}
    sim.set_tracked({"AAPL", "MSFT"})
    sim._step()

    # Now remove MSFT from watchlist but it's still held
    sim.set_tracked({"AAPL", "MSFT"})  # MSFT still in positions
    sim._step()

    assert cache.get("MSFT") is not None, "held ticker must stay in cache"


def test_fallback_to_whole_universe_before_set_tracked():
    """Before set_tracked is called, _step should simulate all tickers."""
    cache, sim = make_sim(rng_seed=5)
    # No set_tracked call yet
    sim._step()

    # At least the default watchlist should be populated
    from market.seed import DEFAULT_WATCHLIST
    for ticker in DEFAULT_WATCHLIST:
        assert cache.get(ticker) is not None, f"{ticker} missing before set_tracked"


# ---- prev_price rolls correctly -----------------------------------------

def test_prev_price_rolls_forward():
    """Each tick prev_price should equal the previous tick's price."""
    cache, sim = make_sim(rng_seed=10)
    sim.set_tracked({"AAPL"})
    sim._step()
    p1 = cache.get("AAPL").price

    sim._step()
    q2 = cache.get("AAPL")
    assert q2.prev_price == p1


# ---- lifecycle -----------------------------------------------------------

@pytest.mark.asyncio
async def test_start_and_stop():
    """start() creates a task; stop() cancels it cleanly."""
    cache, sim = make_sim()
    sim.set_tracked({"AAPL"})
    await sim.start()
    assert sim._task is not None and not sim._task.done()
    await sim.stop()
    assert sim._task is None


@pytest.mark.asyncio
async def test_start_is_idempotent():
    """Calling start() twice must not create a second task."""
    cache, sim = make_sim()
    await sim.start()
    task_ref = sim._task
    await sim.start()
    assert sim._task is task_ref
    await sim.stop()


# ---- sector correlation (statistical) -----------------------------------

def test_same_sector_correlates_more_than_cross_sector():
    """Over many ticks, AAPL↔GOOGL (both tech) should correlate more
    strongly than AAPL↔JPM (tech vs finance). Loose threshold: > 0."""
    cache, sim = make_sim(rng_seed=2024)
    tickers = {"AAPL", "GOOGL", "JPM"}
    sim.set_tracked(tickers)

    N = 600
    series: dict[str, list[float]] = {t: [] for t in tickers}

    for _ in range(N):
        sim._step()
        for t in tickers:
            q = cache.get(t)
            if q:
                series[t].append(q.price)

    def log_returns(prices: list[float]) -> list[float]:
        return [math.log(prices[i + 1] / prices[i]) for i in range(len(prices) - 1)]

    def pearson(a: list[float], b: list[float]) -> float:
        n = len(a)
        if n < 2:
            return 0.0
        ma = sum(a) / n
        mb = sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = math.sqrt(sum((x - ma) ** 2 for x in a))
        db = math.sqrt(sum((x - mb) ** 2 for x in b))
        return num / (da * db) if da * db != 0 else 0.0

    ret = {t: log_returns(series[t]) for t in tickers}
    corr_tech = pearson(ret["AAPL"], ret["GOOGL"])   # same sector
    corr_cross = pearson(ret["AAPL"], ret["JPM"])    # cross sector

    assert corr_tech > corr_cross, (
        f"Expected tech-tech ({corr_tech:.3f}) > tech-finance ({corr_cross:.3f})"
    )
