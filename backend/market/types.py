from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


@dataclass(frozen=True)
class Quote:
    """Latest known price for one ticker. Stored in the cache, pushed over SSE.
    Prices are USD. Immutable — the cache replaces, never mutates."""

    ticker: str
    price: float
    prev_price: float
    reference_price: float  # first price seen this process; stable for life of process
    timestamp: float        # Unix seconds

    @property
    def direction(self) -> Direction:
        if self.price > self.prev_price:
            return Direction.UP
        if self.price < self.prev_price:
            return Direction.DOWN
        return Direction.FLAT

    @property
    def change(self) -> float:
        """Absolute change vs session reference price."""
        return self.price - self.reference_price

    @property
    def change_pct(self) -> float:
        """Watchlist 'change %' — vs session reference price (not avg_cost)."""
        if self.reference_price == 0:
            return 0.0
        return (self.price - self.reference_price) / self.reference_price * 100.0
