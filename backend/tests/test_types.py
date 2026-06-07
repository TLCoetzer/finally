"""Unit tests for market.types — Quote and Direction."""
import pytest
from market.types import Direction, Quote


# ---- Direction -----------------------------------------------------------

def test_direction_values():
    assert Direction.UP.value == "up"
    assert Direction.DOWN.value == "down"
    assert Direction.FLAT.value == "flat"


# ---- Quote.direction -----------------------------------------------------

def test_direction_up():
    q = Quote("AAPL", price=191.0, prev_price=190.0, reference_price=190.0, timestamp=1.0)
    assert q.direction == Direction.UP


def test_direction_down():
    q = Quote("AAPL", price=189.0, prev_price=190.0, reference_price=190.0, timestamp=1.0)
    assert q.direction == Direction.DOWN


def test_direction_flat():
    q = Quote("AAPL", price=190.0, prev_price=190.0, reference_price=190.0, timestamp=1.0)
    assert q.direction == Direction.FLAT


# ---- Quote.change and change_pct -----------------------------------------

def test_change():
    q = Quote("AAPL", price=200.0, prev_price=195.0, reference_price=190.0, timestamp=1.0)
    assert q.change == pytest.approx(10.0)


def test_change_pct_positive():
    q = Quote("AAPL", price=200.0, prev_price=195.0, reference_price=100.0, timestamp=1.0)
    assert q.change_pct == pytest.approx(100.0)


def test_change_pct_negative():
    q = Quote("AAPL", price=95.0, prev_price=100.0, reference_price=100.0, timestamp=1.0)
    assert q.change_pct == pytest.approx(-5.0)


def test_change_pct_zero_reference():
    q = Quote("AAPL", price=100.0, prev_price=100.0, reference_price=0.0, timestamp=1.0)
    assert q.change_pct == 0.0


def test_change_pct_flat():
    q = Quote("AAPL", price=190.0, prev_price=185.0, reference_price=190.0, timestamp=1.0)
    assert q.change_pct == pytest.approx(0.0)


# ---- Quote is immutable (frozen dataclass) --------------------------------

def test_quote_is_frozen():
    q = Quote("AAPL", price=190.0, prev_price=190.0, reference_price=190.0, timestamp=1.0)
    with pytest.raises((AttributeError, TypeError)):
        q.price = 200.0  # type: ignore[misc]
