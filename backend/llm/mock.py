"""Deterministic mock LLM (LLM_MOCK=true) for tests/CI/dev (PLAN.md §9).

No network, no API key. The response is chosen by simple keyword matching on the
user message so E2E tests can deterministically exercise: a plain reply, a trade
execution, and a watchlist add. Output is the same ChatResponse shape the real
model returns, so it flows through the identical execution path.
"""
from __future__ import annotations

import re

from .schema import (
    ChatResponse,
    Side,
    TradeInstruction,
    WatchlistAction,
    WatchlistChange,
)

# Defaults when the message names no ticker.
_DEFAULT_TRADE_TICKER = "AAPL"
_DEFAULT_WATCH_TICKER = "PYPL"
_MOCK_QTY = 1.0

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
# Common all-caps words that are not tickers, to avoid false positives.
_STOPWORDS = {"AI", "I", "A", "P", "L", "PNL", "USD", "FINALLY", "OK"}


def mock_response(user_message: str) -> ChatResponse:
    """Deterministic ChatResponse keyed off the user's message.

    - "buy"  -> a buy trade
    - "sell" -> a sell trade
    - "watch"/"add" -> a watchlist add
    - otherwise -> a plain analytical reply
    A ticker named in caps (e.g. "buy 1 TSLA") is honored; otherwise a default
    is used. Matching is deterministic for reproducible tests."""
    lowered = user_message.lower()

    if "buy" in lowered:
        ticker = _extract_ticker(user_message, _DEFAULT_TRADE_TICKER)
        return ChatResponse(
            message=f"Buying {_MOCK_QTY:g} share of {ticker} for you.",
            trades=[TradeInstruction(ticker=ticker, side=Side.BUY, quantity=_MOCK_QTY)],
        )

    if "sell" in lowered:
        ticker = _extract_ticker(user_message, _DEFAULT_TRADE_TICKER)
        return ChatResponse(
            message=f"Selling {_MOCK_QTY:g} share of {ticker} for you.",
            trades=[TradeInstruction(ticker=ticker, side=Side.SELL, quantity=_MOCK_QTY)],
        )

    if "watch" in lowered or "add" in lowered:
        ticker = _extract_ticker(user_message, _DEFAULT_WATCH_TICKER)
        return ChatResponse(
            message=f"Adding {ticker} to your watchlist.",
            watchlist_changes=[
                WatchlistChange(ticker=ticker, action=WatchlistAction.ADD)
            ],
        )

    return ChatResponse(
        message=(
            "Your portfolio looks balanced. Ask me to analyze a position, "
            "buy or sell shares, or add a ticker to your watchlist."
        )
    )


def _extract_ticker(message: str, default: str) -> str:
    """First plausible all-caps ticker token in the message, else `default`."""
    for match in _TICKER_RE.findall(message):
        if match not in _STOPWORDS:
            return match
    return default
