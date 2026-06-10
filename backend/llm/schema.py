"""Structured-output schema for the chat LLM (PLAN.md §9).

The LLM is asked to return JSON matching `ChatResponse`. Trades and watchlist
changes are optional; an empty/absent list means "no action". These models are
also reused as the response_format passed to LiteLLM for structured outputs.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class WatchlistAction(str, Enum):
    ADD = "add"
    REMOVE = "remove"


class TradeInstruction(BaseModel):
    ticker: str
    side: Side
    quantity: float = Field(gt=0)

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class WatchlistChange(BaseModel):
    ticker: str
    action: WatchlistAction

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class ChatResponse(BaseModel):
    """What the LLM returns and what we parse. `message` is the only required
    field; trades / watchlist_changes default to empty."""

    message: str
    trades: list[TradeInstruction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)
