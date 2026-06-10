"""Periodic portfolio-value snapshot task (PLAN.md §7).

Records a portfolio_snapshots row every 30s so the P&L history has regular
data points (trades also record one immediately — that path lives in the DB
layer). total_value is computed the same way as GET /api/portfolio via
build_portfolio, so the snapshot and the live view never disagree.

DB writes go through a thread executor: SQLite calls are blocking and must not
stall the event loop (PLAN.md §7 Concurrency)."""
from __future__ import annotations

import asyncio
import logging

import db
from market.cache import PriceCache
from api.portfolio import build_portfolio

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 30.0  # seconds (PLAN.md §7)


def _build_and_record(cache: PriceCache) -> None:
    """Compute the market-priced total and persist it. Runs in a worker thread
    so the blocking DB reads/writes never touch the event loop."""
    db.record_snapshot(build_portfolio(cache).total_value)


async def _record_once(cache: PriceCache) -> None:
    await asyncio.to_thread(_build_and_record, cache)


async def snapshot_loop(cache: PriceCache, interval: float = SNAPSHOT_INTERVAL) -> None:
    """Record a portfolio snapshot every `interval` seconds until cancelled.
    Exceptions are logged and swallowed so a transient DB hiccup can't kill
    the loop."""
    while True:
        await asyncio.sleep(interval)
        try:
            await _record_once(cache)
        except Exception:  # noqa: BLE001 — keep the loop alive
            logger.exception("portfolio snapshot failed")
