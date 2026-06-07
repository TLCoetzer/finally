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

    def __init__(self, spec: TickerSpec) -> None:
        self.spec = spec
        self.price = spec.seed_price  # full-precision internal price


class SimulatorProvider(MarketDataProvider):
    """In-process GBM price simulator. Default provider when no MASSIVE_API_KEY.

    Uses Geometric Brownian Motion with correlated market/sector factors and
    occasional random shock events for drama. Inject a seeded random.Random
    to get a fully reproducible sequence in tests."""

    def __init__(
        self,
        cache: PriceCache,
        tick_seconds: float = 0.5,
        w_market: float = 0.4,
        w_sector: float = 0.3,
        event_prob: float = 0.001,  # ~1 shock / 16 min / ticker at 500ms ticks
        rng: random.Random | None = None,
    ) -> None:
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
                pass  # never kill the loop on a bad tick
            await asyncio.sleep(self._tick)

    # ---- one GBM tick ----------------------------------------------------

    def _step(self) -> None:
        """Advance every tracked ticker by one GBM step and write to cache."""
        dt = self._tick / SECONDS_PER_YEAR
        sqrt_dt = math.sqrt(dt)
        now = time.time()

        z_market = self._rng.gauss(0.0, 1.0)
        sectors = {s.spec.sector for s in self._state.values()}
        z_sector = {sec: self._rng.gauss(0.0, 1.0) for sec in sectors}
        w_idio = 1.0 - self._w_market - self._w_sector

        # Simulate the tracked union; fall back to whole universe before
        # set_tracked is first called so the first SSE frames are populated.
        targets = self._tracked or set(self._state)

        for ticker in targets:
            st = self._state.get(ticker)
            if st is None:
                continue  # ticker not in the simulator universe; skip
            spec = st.spec

            z = (
                math.sqrt(self._w_market) * z_market
                + math.sqrt(self._w_sector) * z_sector[spec.sector]
                + math.sqrt(w_idio) * self._rng.gauss(0.0, 1.0)
            )
            drift = (spec.annual_drift - 0.5 * spec.annual_vol ** 2) * dt
            diffusion = spec.annual_vol * sqrt_dt * z
            st.price *= math.exp(drift + diffusion)

            if self._rng.random() < self._event_prob:
                shock = self._rng.uniform(0.02, 0.05) * self._rng.choice((-1, 1))
                st.price *= (1.0 + shock)

            # Round to cents on the wire; internal state stays full-precision.
            self.cache.update(ticker, round(st.price, 2), now)

    # ---- validation ------------------------------------------------------

    async def is_supported(self, ticker: str) -> bool:
        return ticker.upper() in UNIVERSE
