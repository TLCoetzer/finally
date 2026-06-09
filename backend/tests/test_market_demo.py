"""Unit tests for demo.market_demo pure helpers (no rich dependency needed)."""
from demo.market_demo import (
    SPARK_CHARS,
    direction_glyph,
    resolve_tickers,
    sparkline,
)
from market.seed import DEFAULT_WATCHLIST
from market.types import Direction


# ---- sparkline -----------------------------------------------------------

def test_sparkline_empty():
    assert sparkline([]) == ""


def test_sparkline_flat_series_uses_lowest_block():
    assert sparkline([5.0, 5.0, 5.0]) == SPARK_CHARS[0] * 3


def test_sparkline_length_matches_input():
    assert len(sparkline([1.0, 2.0, 3.0, 4.0])) == 4


def test_sparkline_low_and_high_map_to_ends():
    spark = sparkline([1.0, 2.0, 3.0])
    assert spark[0] == SPARK_CHARS[0]      # min → lowest block
    assert spark[-1] == SPARK_CHARS[-1]    # max → highest block


def test_sparkline_ignores_none():
    assert len(sparkline([1.0, None, 2.0])) == 2


# ---- resolve_tickers -----------------------------------------------------

def test_resolve_tickers_default_when_empty():
    assert resolve_tickers(None) == list(DEFAULT_WATCHLIST)
    assert resolve_tickers("") == list(DEFAULT_WATCHLIST)


def test_resolve_tickers_filters_and_uppercases():
    assert resolve_tickers("aapl, nvda") == ["AAPL", "NVDA"]


def test_resolve_tickers_drops_unknown():
    assert resolve_tickers("AAPL,ZZZZ,MSFT") == ["AAPL", "MSFT"]


def test_resolve_tickers_all_unknown_falls_back():
    assert resolve_tickers("ZZZZ,YYYY") == list(DEFAULT_WATCHLIST)


# ---- direction_glyph -----------------------------------------------------

def test_direction_glyph_up_down_flat():
    up_arrow, up_style = direction_glyph(Direction.UP)
    down_arrow, _ = direction_glyph(Direction.DOWN)
    flat_arrow, _ = direction_glyph(Direction.FLAT)
    assert up_arrow == "▲" and "green" in up_style
    assert down_arrow == "▼"
    assert flat_arrow == "—"
