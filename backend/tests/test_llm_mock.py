"""Mock LLM tests: determinism and coverage of plain/trade/watchlist branches."""
from __future__ import annotations

from llm.client import generate, mock_enabled
from llm.mock import mock_response
from llm.prompt import PortfolioContext
from llm.schema import Side, WatchlistAction


def test_plain_reply_has_no_actions():
    r = mock_response("How is my portfolio doing?")
    assert r.message
    assert r.trades == []
    assert r.watchlist_changes == []


def test_buy_branch_emits_buy_trade():
    r = mock_response("Please buy some shares")
    assert len(r.trades) == 1
    assert r.trades[0].side is Side.BUY
    assert r.trades[0].quantity > 0


def test_sell_branch_emits_sell_trade():
    r = mock_response("sell my position")
    assert len(r.trades) == 1
    assert r.trades[0].side is Side.SELL


def test_watchlist_branch_emits_add():
    r = mock_response("add to my watchlist")
    assert len(r.watchlist_changes) == 1
    assert r.watchlist_changes[0].action is WatchlistAction.ADD


def test_named_ticker_is_honored():
    r = mock_response("buy 1 TSLA")
    assert r.trades[0].ticker == "TSLA"


def test_mock_is_deterministic():
    a = mock_response("buy 1 NVDA")
    b = mock_response("buy 1 NVDA")
    assert a.model_dump() == b.model_dump()


def test_generate_uses_mock_when_enabled(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    assert mock_enabled() is True
    r = generate(PortfolioContext(cash=10000.0), [], "buy 1 AAPL")
    assert r.trades[0].side is Side.BUY
    assert r.trades[0].ticker == "AAPL"


def test_mock_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    assert mock_enabled() is False
