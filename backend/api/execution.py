"""Shared trade-execution path (PLAN.md §7, §9).

ONE entry point used by both POST /api/portfolio/trade and the LLM chat
auto-execution flow, so manual and AI-initiated trades share identical pricing,
validation, and persistence. Callers wrap this and translate TradeError into
their own surface (HTTP 400 for the route, an inline error for chat).

Market orders only: the fill price is the latest cached price. db.execute_trade
owns the cash/position math, the trades-row append, and the post-trade
portfolio_snapshots row (PLAN.md §7). recompute_tracked is the CALLER's job
(the route/chat handler has the app)."""
from __future__ import annotations

import db
from market.cache import PriceCache
from api.schemas import TradeResponse


class TradeError(Exception):
    """A trade rejected by validation (insufficient cash/shares, no price)."""


def execute_trade(
    cache: PriceCache, ticker: str, side: str, quantity: float
) -> TradeResponse:
    """Fill a market order at the latest cached price and persist it.

    Raises TradeError if the ticker has no price yet or the DB layer rejects
    the trade (insufficient cash on buy, insufficient shares on sell). The DB
    reports rejections in-band ({"ok": False, "reason": ...}); we translate
    that into TradeError so callers have one failure surface."""
    ticker = ticker.upper()
    quote = cache.get(ticker)
    if quote is None:
        raise TradeError(f"No price available for {ticker}")
    price = quote.price
    result = db.execute_trade(ticker, side, quantity, price)
    if not result["ok"]:  # DB layer reports rejection in-band, not via exception
        raise TradeError(result["reason"])
    trade = result["trade"]
    return TradeResponse(
        ticker=trade["ticker"],
        side=trade["side"],
        quantity=trade["quantity"],
        price=trade["price"],
        executed_at=trade["executed_at"],
        cash=result["cash_balance"],
    )
