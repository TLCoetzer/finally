"""Chat orchestration: context -> LLM -> auto-execute -> persist (PLAN.md §9).

This sits between the framework-free LLM core (prompt/parser/mock/client) and the
DB + shared trade-execution path. It is deliberately thin and dependency-injected
so it can be unit-tested without FastAPI: the route passes in the live PriceCache,
the provider's `is_supported`, and the shared `execute_trade` callable.

Flow per PLAN.md §9:
  1. build portfolio context (cash, positions w/ P&L, watchlist w/ live prices)
  2. load last 20 chat messages
  3. call the LLM (or mock) for a structured ChatResponse
  4. auto-execute trades and watchlist changes through the SAME path as manual
     actions; collect per-action outcomes (failures included, not raised)
  5. persist the user message and the assistant message (+ actions JSON)
  6. return message + executed actions
"""
from __future__ import annotations

import asyncio
from typing import Callable

import db
from market.cache import PriceCache

from . import client
from .prompt import (
    ChatTurn,
    PortfolioContext,
    PositionView,
    WatchlistView,
)
from .schema import ChatResponse, Side, WatchlistAction

# Signature of the shared trade-execution path (api.execution.execute_trade):
# returns an object exposing .ticker/.side/.quantity/.price, raises on rejection.
TradeFn = Callable[[PriceCache, str, str, float], object]
# The exception type TradeFn raises on a rejected trade (api.execution.TradeError).
TradeErr = type[Exception]


def build_context(cache: PriceCache) -> PortfolioContext:
    """Assemble the live portfolio context from the DB and price cache."""
    cash = db.get_cash()
    positions = [
        PositionView(
            ticker=p["ticker"],
            quantity=p["quantity"],
            avg_cost=p["avg_cost"],
            current_price=_price(cache, p["ticker"]),
        )
        for p in db.list_positions()
    ]
    watchlist = [
        WatchlistView(
            ticker=t,
            price=_price(cache, t),
            change_pct=_change_pct(cache, t),
        )
        for t in db.watchlist_tickers()
    ]
    return PortfolioContext(cash=cash, positions=positions, watchlist=watchlist)


def _price(cache: PriceCache, ticker: str) -> float | None:
    q = cache.get(ticker)
    return q.price if q else None


def _change_pct(cache: PriceCache, ticker: str) -> float | None:
    q = cache.get(ticker)
    return q.change_pct if q else None


def load_history(limit: int = 20) -> list[ChatTurn]:
    """Last `limit` messages as oldest-first ChatTurns (db.recent_chat order)."""
    return [ChatTurn(role=m["role"], content=m["content"]) for m in db.recent_chat(limit)]


async def run_chat(
    user_message: str,
    *,
    cache: PriceCache,
    execute_trade: TradeFn,
    trade_error: TradeErr,
    is_supported,            # async Callable[[str], bool]
    on_change: Callable[[], None],  # recompute_tracked(app) — called after any mutation
) -> tuple[str, list[dict]]:
    """Run one chat turn end to end. Returns (assistant_message, actions).

    `actions` is a list of plain dicts matching api.schemas.ExecutedAction so the
    route can build response models and the same list is persisted as the
    assistant message's actions JSON. Trade/watchlist failures are captured as
    `ok=False` actions, never raised — the LLM/user is informed inline."""
    # build_context + load_history hit blocking SQLite; client.generate may do a
    # network call. Offload them so the event loop stays responsive.
    ctx = await asyncio.to_thread(build_context, cache)
    history = await asyncio.to_thread(load_history, 20)

    reply: ChatResponse = await asyncio.to_thread(
        client.generate, ctx, history, user_message
    )

    actions: list[dict] = []
    mutated = False

    for trade in reply.trades:
        action = await asyncio.to_thread(
            _apply_trade, trade, cache, execute_trade, trade_error
        )
        actions.append(action)
        if action["ok"]:
            mutated = True

    for change in reply.watchlist_changes:
        action = await _apply_watchlist_change(change, is_supported)
        actions.append(action)
        if action["ok"]:
            mutated = True

    if mutated:
        on_change()  # re-derive tracked set so new holds/watches start streaming

    await asyncio.to_thread(db.append_chat, "user", user_message)
    await asyncio.to_thread(db.append_chat, "assistant", reply.message, actions or None)

    return reply.message, actions


def _apply_trade(trade, cache, execute_trade: TradeFn, trade_error: TradeErr) -> dict:
    try:
        result = execute_trade(cache, trade.ticker, trade.side.value, trade.quantity)
    except trade_error as exc:
        return {
            "kind": "trade",
            "ok": False,
            "summary": f"{trade.side.value.capitalize()} {trade.quantity:g} "
            f"{trade.ticker} rejected",
            "detail": str(exc),
        }
    verb = "Bought" if trade.side is Side.BUY else "Sold"
    return {
        "kind": "trade",
        "ok": True,
        "summary": f"{verb} {result.quantity:g} {result.ticker} @ ${result.price:,.2f}",
        "detail": None,
    }


async def _apply_watchlist_change(change, is_supported) -> dict:
    ticker = change.ticker
    if change.action is WatchlistAction.ADD:
        if not await is_supported(ticker):
            return {
                "kind": "watchlist",
                "ok": False,
                "summary": f"Add {ticker} to watchlist rejected",
                "detail": f"Ticker not supported: {ticker}",
            }
        await asyncio.to_thread(db.add_watchlist, ticker)
        return {
            "kind": "watchlist",
            "ok": True,
            "summary": f"Added {ticker} to watchlist",
            "detail": None,
        }
    # remove
    removed = await asyncio.to_thread(db.remove_watchlist, ticker)
    return {
        "kind": "watchlist",
        "ok": True,
        "summary": f"Removed {ticker} from watchlist"
        if removed
        else f"{ticker} was not on the watchlist",
        "detail": None,
    }
