"""Pydantic request/response models for the REST API (PLAN.md §8).

Kept separate from the routers so models read as one contract and tests can
import them without pulling in route dependencies."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---- watchlist -----------------------------------------------------------

class WatchlistAdd(BaseModel):
    ticker: str = Field(..., min_length=1)


class WatchlistItem(BaseModel):
    """A watched ticker with its latest cached quote (None until first tick)."""
    ticker: str
    price: float | None = None
    reference_price: float | None = None
    change_pct: float | None = None
    direction: str | None = None


class WatchlistResponse(BaseModel):
    tickers: list[WatchlistItem]


# ---- portfolio -----------------------------------------------------------

class PositionItem(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    price: float | None = None          # current price from cache (None until first tick)
    market_value: float | None = None   # price * quantity
    unrealized_pnl: float | None = None  # (price - avg_cost) * quantity
    change_pct: float | None = None      # gain/loss vs avg_cost (PLAN.md §10)


class PortfolioResponse(BaseModel):
    cash: float
    positions: list[PositionItem]
    total_value: float  # cash + sum(market_value); falls back to cost when unpriced


# ---- trade ---------------------------------------------------------------

class TradeRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0)
    side: str  # "buy" | "sell"


class TradeResponse(BaseModel):
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str
    cash: float


# ---- health --------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    source: str  # "simulator" | "massive"


# ---- chat (PLAN.md §9) ---------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ExecutedAction(BaseModel):
    """One auto-executed action and its outcome, surfaced inline in the chat
    response (and persisted in chat_messages.actions). `ok=False` carries the
    rejection reason so the user learns why a trade/watchlist change failed."""
    kind: str            # "trade" | "watchlist"
    ok: bool
    summary: str         # human-readable, e.g. "Bought 10 AAPL @ $190.00"
    detail: str | None = None  # rejection reason when ok is False


class ChatResponseModel(BaseModel):
    message: str
    actions: list[ExecutedAction] = Field(default_factory=list)
