"""Unit tests for the SQLite data-access layer (db.py, PLAN.md §7)."""
from __future__ import annotations

import sqlite3

import pytest

import db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point db at a throwaway file and reset the shared connection."""
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    db.reset_for_tests()
    db.init_if_needed()
    yield
    db.reset_for_tests()


# --- schema / seed -----------------------------------------------------------

def test_seed_creates_default_user_and_cash(fresh_db):
    assert db.get_cash() == db.DEFAULT_CASH


def test_seed_creates_default_watchlist(fresh_db):
    assert db.watchlist_tickers() == [
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    ]


def test_init_is_idempotent(fresh_db):
    db.init_if_needed()
    db.init_if_needed()
    assert db.get_cash() == db.DEFAULT_CASH
    assert len(db.watchlist_tickers()) == 10


def test_wal_mode_enabled(fresh_db):
    conn = db._require_conn()
    with db._lock:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_db_path_env_override(tmp_path, monkeypatch):
    target = tmp_path / "custom" / "mydb.sqlite"
    monkeypatch.setenv("FINALLY_DB_PATH", str(target))
    db.reset_for_tests()
    db.init_if_needed()
    try:
        assert target.exists()
    finally:
        db.reset_for_tests()


# --- watchlist ---------------------------------------------------------------

def test_add_watchlist_new(fresh_db):
    row = db.add_watchlist("amd")
    assert row["ticker"] == "AMD"
    assert "AMD" in db.watchlist_tickers()


def test_add_watchlist_idempotent(fresh_db):
    first = db.add_watchlist("AMD")
    second = db.add_watchlist("amd")
    assert first["added_at"] == second["added_at"]
    assert db.watchlist_tickers().count("AMD") == 1


def test_remove_watchlist(fresh_db):
    assert db.remove_watchlist("AAPL") is True
    assert "AAPL" not in db.watchlist_tickers()
    assert db.remove_watchlist("AAPL") is False


def test_list_watchlist_shape(fresh_db):
    rows = db.list_watchlist()
    assert len(rows) == 10
    assert set(rows[0]) == {"ticker", "added_at"}


# --- positions / buys --------------------------------------------------------

def test_buy_creates_position_and_deducts_cash(fresh_db):
    res = db.execute_trade("AAPL", "buy", 10, 100.0)
    assert res["ok"] is True
    assert res["cash_balance"] == pytest.approx(10000.0 - 1000.0)
    pos = db.get_position("AAPL")
    assert pos["quantity"] == 10
    assert pos["avg_cost"] == 100.0
    assert "AAPL" in db.position_tickers()


def test_buy_weighted_average_cost(fresh_db):
    db.execute_trade("AAPL", "buy", 10, 100.0)
    db.execute_trade("AAPL", "buy", 30, 200.0)
    pos = db.get_position("AAPL")
    assert pos["quantity"] == 40
    # (10*100 + 30*200) / 40 = 175
    assert pos["avg_cost"] == pytest.approx(175.0)


def test_buy_insufficient_cash_rejected(fresh_db):
    res = db.execute_trade("AAPL", "buy", 1000, 100.0)
    assert res["ok"] is False
    assert res["reason"] == "insufficient cash"
    assert db.get_cash() == db.DEFAULT_CASH
    assert db.get_position("AAPL") is None


# --- sells -------------------------------------------------------------------

def test_sell_adds_cash_keeps_avg_cost(fresh_db):
    db.execute_trade("AAPL", "buy", 10, 100.0)
    res = db.execute_trade("AAPL", "sell", 4, 150.0)
    assert res["ok"] is True
    # cash: 10000 - 1000 (buy) + 600 (sell) = 9600
    assert res["cash_balance"] == pytest.approx(9600.0)
    pos = db.get_position("AAPL")
    assert pos["quantity"] == 6
    assert pos["avg_cost"] == 100.0  # unchanged by sells


def test_sell_at_loss(fresh_db):
    db.execute_trade("AAPL", "buy", 10, 100.0)
    res = db.execute_trade("AAPL", "sell", 10, 80.0)
    assert res["ok"] is True
    # 10000 - 1000 + 800 = 9800
    assert res["cash_balance"] == pytest.approx(9800.0)


def test_full_sell_deletes_position_row(fresh_db):
    db.execute_trade("AAPL", "buy", 10, 100.0)
    res = db.execute_trade("AAPL", "sell", 10, 120.0)
    assert res["ok"] is True
    assert res["position"] is None
    assert db.get_position("AAPL") is None
    assert "AAPL" not in db.position_tickers()


def test_sell_more_than_owned_rejected(fresh_db):
    db.execute_trade("AAPL", "buy", 5, 100.0)
    res = db.execute_trade("AAPL", "sell", 10, 100.0)
    assert res["ok"] is False
    assert res["reason"] == "insufficient shares"
    assert db.get_position("AAPL")["quantity"] == 5


def test_sell_with_no_position_rejected(fresh_db):
    res = db.execute_trade("MSFT", "sell", 1, 100.0)
    assert res["ok"] is False
    assert res["reason"] == "insufficient shares"


# --- input validation --------------------------------------------------------

@pytest.mark.parametrize("side", ["hold", "", "BUYY"])
def test_invalid_side_rejected(fresh_db, side):
    res = db.execute_trade("AAPL", side, 1, 100.0)
    assert res["ok"] is False


@pytest.mark.parametrize("qty,price", [(0, 100.0), (-1, 100.0), (1, 0), (1, -5)])
def test_non_positive_qty_or_price_rejected(fresh_db, qty, price):
    res = db.execute_trade("AAPL", "buy", qty, price)
    assert res["ok"] is False


# --- snapshots / trades log --------------------------------------------------

def test_trade_appends_trade_and_snapshot_rows(fresh_db):
    db.execute_trade("AAPL", "buy", 10, 100.0)
    conn = db._require_conn()
    with db._lock:
        trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        snaps = conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0]
    assert trades == 1
    assert snaps == 1


def test_record_snapshot(fresh_db):
    db.record_snapshot(12345.67)
    conn = db._require_conn()
    with db._lock:
        row = conn.execute(
            "SELECT total_value FROM portfolio_snapshots"
        ).fetchone()
    assert row["total_value"] == pytest.approx(12345.67)


# --- chat --------------------------------------------------------------------

def test_append_and_recent_chat_order(fresh_db):
    db.append_chat("user", "hello")
    db.append_chat("assistant", "hi", actions={"trades": []})
    msgs = db.recent_chat()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["actions"] is None
    assert msgs[1]["actions"] == {"trades": []}


def test_recent_chat_caps_at_limit(fresh_db):
    for i in range(30):
        db.append_chat("user", f"msg {i}")
    msgs = db.recent_chat(20)
    assert len(msgs) == 20
    # chronological: the 20 most recent are msgs 10..29
    assert msgs[0]["content"] == "msg 10"
    assert msgs[-1]["content"] == "msg 29"


def test_recent_chat_default_limit_is_20(fresh_db):
    for i in range(25):
        db.append_chat("user", f"m{i}")
    assert len(db.recent_chat()) == 20
