"""Tests for the periodic portfolio-snapshot task (PLAN.md §7)."""
from __future__ import annotations

import sqlite3

import pytest

import db
from market.cache import PriceCache
from api.snapshots import _record_once, snapshot_loop


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    db.reset_for_tests()
    db.init_if_needed()
    yield
    db.reset_for_tests()


def _snapshot_rows() -> list[sqlite3.Row]:
    conn = db._require_conn()
    with db._lock:
        return conn.execute(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id=?",
            (db.DEFAULT_USER,),
        ).fetchall()


async def test_record_once_writes_market_priced_total(fresh_db):
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    db.execute_trade("AAPL", "buy", 10, 190.0)  # cash 8100, 10 @ 190
    cache.update("AAPL", 200.0)                  # price moves up

    before = len(_snapshot_rows())
    await _record_once(cache)
    rows = _snapshot_rows()
    assert len(rows) == before + 1
    # total = cash 8100 + 10*200 (market price, not avg_cost) = 10100
    assert rows[-1]["total_value"] == pytest.approx(10100.0)


async def test_record_once_fresh_portfolio_is_cash(fresh_db):
    cache = PriceCache()
    await _record_once(cache)
    assert _snapshot_rows()[-1]["total_value"] == pytest.approx(10000.0)


async def test_snapshot_loop_records_then_cancels(fresh_db):
    import asyncio

    cache = PriceCache()
    task = asyncio.create_task(snapshot_loop(cache, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(_snapshot_rows()) >= 1
