"""Watchlist routes (PLAN.md §8).

GET returns watched tickers joined with their latest cached quote. POST gates
adds on the active provider's supported universe (`is_supported`, §6) and
rejects unknown tickers with 400. Every mutation re-derives the tracked set so
newly watched tickers start streaming and removals stop (unless still held)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

import db
from market.cache import PriceCache
from market.provider import MarketDataProvider
from tracking import recompute_tracked
from api.deps import get_cache, get_provider
from api.schemas import WatchlistAdd, WatchlistItem, WatchlistResponse

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _item(ticker: str, cache: PriceCache) -> WatchlistItem:
    q = cache.get(ticker)
    if q is None:
        return WatchlistItem(ticker=ticker.upper())
    return WatchlistItem(
        ticker=q.ticker,
        price=q.price,
        reference_price=q.reference_price,
        change_pct=q.change_pct,
        direction=q.direction.value,
    )


@router.get("")
def get_watchlist(cache: PriceCache = Depends(get_cache)) -> WatchlistResponse:
    return WatchlistResponse(
        tickers=[_item(t, cache) for t in db.watchlist_tickers()]
    )


@router.post("", status_code=201)
async def add_watchlist(
    body: WatchlistAdd,
    request: Request,
    provider: MarketDataProvider = Depends(get_provider),
    cache: PriceCache = Depends(get_cache),
) -> WatchlistItem:
    ticker = body.ticker.strip().upper()
    if not await provider.is_supported(ticker):
        raise HTTPException(status_code=400, detail=f"Ticker not supported: {ticker}")
    await asyncio.to_thread(db.add_watchlist, ticker)  # blocking SQLite off the loop
    recompute_tracked(request.app)  # start streaming the new ticker
    return _item(ticker, cache)


@router.delete("/{ticker}", status_code=204)
def remove_watchlist(ticker: str, request: Request) -> None:
    db.remove_watchlist(ticker.strip().upper())
    recompute_tracked(request.app)  # held tickers stay cached via positions
