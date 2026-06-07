from __future__ import annotations
import asyncio

import httpx

from .provider import MarketDataProvider
from .cache import PriceCache

BASE = "https://api.massive.com"


class MassiveProvider(MarketDataProvider):
    """Live market data from the Massive (Polygon.io) REST API.

    One batched snapshot request per cycle refreshes every tracked ticker —
    free-tier safe at ~4 req/min with the default 15 s poll interval."""

    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        poll_seconds: float = 15.0,
    ) -> None:
        super().__init__(cache)
        self._api_key = api_key
        self._poll = poll_seconds
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {api_key}"},  # key never in logs/URL
            timeout=10.0,  # finite — never hang the loop
        )
        self._supported: dict[str, bool] = {}  # memoised is_supported answers

    @property
    def source(self) -> str:
        return "massive"

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
        await self._client.aclose()

    async def _loop(self) -> None:
        backoff = self._poll
        while True:
            try:
                await self._poll_once()
                backoff = self._poll  # recovered — restore base interval
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    backoff = min(backoff * 2, 60.0)  # rate-limit backoff
            except Exception:
                pass  # network blip — keep last cache values, never crash
            await asyncio.sleep(backoff)

    async def _poll_once(self) -> None:
        """Fetch one batched snapshot for all tracked tickers and update cache."""
        tickers = self.tracked
        if not tickers:
            return
        r = await self._client.get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"tickers": ",".join(sorted(tickers))},  # one batched call
        )
        r.raise_for_status()
        for snap in r.json().get("tickers", []):
            price = self._extract_price(snap)
            if price is not None:
                # `updated` is nanoseconds; convert to seconds (MASSIVE_API.md §6)
                ts = (snap.get("updated", 0) / 1_000_000_000) or None
                self.cache.update(snap["ticker"], price, ts)

    @staticmethod
    def _extract_price(snap: dict) -> float | None:
        """Price fallback chain (MASSIVE_API.md §4.1): lastTrade.p → min.c →
        day.c → prevDay.c. First non-null wins."""
        for obj_key, val_key in (
            ("lastTrade", "p"),
            ("min", "c"),
            ("day", "c"),
            ("prevDay", "c"),
        ):
            obj = snap.get(obj_key) or {}
            v = obj.get(val_key)
            if v:
                return float(v)
        return None

    # ---- validation ------------------------------------------------------

    async def is_supported(self, ticker: str) -> bool:
        """True iff the ticker is a supported active stock on Massive.

        Memoised for the process lifetime; fails closed on network error so a
        transient failure never admits an unvalidated symbol."""
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
            ok = False  # fail closed — never admit an unvalidated symbol
        self._supported[t] = ok
        return ok
