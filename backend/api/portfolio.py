"""Portfolio routes (PLAN.md §8, §10).

GET computes the authoritative portfolio snapshot on load/refresh: each
position priced from the cache, unrealized P&L and % change vs avg_cost, plus
cash and total value. POST executes a market order through the shared DB path
and re-derives the tracked set so a newly held ticker starts streaming.

Note: GET /api/portfolio/history is intentionally NOT implemented (deferred,
PLAN.md §13 Open Item)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

import db
from market.cache import PriceCache
from tracking import recompute_tracked
from api.deps import get_cache
from api.schemas import (
    PortfolioResponse,
    PositionItem,
    TradeRequest,
    TradeResponse,
)
from api.execution import TradeError, execute_trade

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _position_item(row, cache: PriceCache) -> PositionItem:
    ticker = row["ticker"]
    quantity = row["quantity"]
    avg_cost = row["avg_cost"]
    q = cache.get(ticker)
    if q is None:
        return PositionItem(ticker=ticker, quantity=quantity, avg_cost=avg_cost)
    market_value = q.price * quantity
    change_pct = (q.price - avg_cost) / avg_cost * 100.0 if avg_cost else 0.0
    return PositionItem(
        ticker=ticker,
        quantity=quantity,
        avg_cost=avg_cost,
        price=q.price,
        market_value=market_value,
        unrealized_pnl=(q.price - avg_cost) * quantity,
        change_pct=change_pct,
    )


def build_portfolio(cache: PriceCache) -> PortfolioResponse:
    """Assemble the priced portfolio snapshot. Shared by the route and the
    background snapshot task so total_value is computed one way only."""
    cash = db.get_cash()
    items = [_position_item(r, cache) for r in db.list_positions()]
    invested = sum(
        i.market_value if i.market_value is not None else i.avg_cost * i.quantity
        for i in items
    )
    return PortfolioResponse(cash=cash, positions=items, total_value=cash + invested)


@router.get("")
def get_portfolio(cache: PriceCache = Depends(get_cache)) -> PortfolioResponse:
    return build_portfolio(cache)


@router.post("/trade")
def trade(body: TradeRequest, request: Request) -> TradeResponse:
    side = body.side.strip().lower()
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail=f"Invalid side: {body.side}")
    cache: PriceCache = request.app.state.cache
    try:
        result = execute_trade(cache, body.ticker.strip().upper(), side, body.quantity)
    except TradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    recompute_tracked(request.app)  # newly held ticker streams; sold-out drops
    return result
