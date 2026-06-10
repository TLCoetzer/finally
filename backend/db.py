"""SQLite data-access layer (PLAN.md §4, §7).

A single shared connection guarded by one lock is the only writer, so the
async runtime never hits ``database is locked``. WAL mode is enabled for
concurrent readers. All public functions are synchronous and fast; async
callers wrap them with ``asyncio.to_thread``.

Lazy init creates the schema and seeds default data on first use. The DB
file path is env-configurable via ``FINALLY_DB_PATH`` (default: the repo
``db/finally.db``; Docker sets ``/app/db/finally.db``).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from market.seed import DEFAULT_WATCHLIST

DEFAULT_USER = "default"
DEFAULT_CASH = 10000.0

_SCHEMA = Path(__file__).with_name("db") / "schema.sql"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    env = os.environ.get("FINALLY_DB_PATH")
    if env:
        return Path(env)
    return _PROJECT_ROOT / "db" / "finally.db"


def _connect() -> sqlite3.Connection:
    """Open the shared connection and apply pragmas. Caller holds ``_lock``."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _seed(conn: sqlite3.Connection) -> None:
    """Insert default user, cash, and the 10-ticker watchlist if absent."""
    conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) "
        "VALUES (?, ?, ?)",
        (DEFAULT_USER, DEFAULT_CASH, _now()),
    )
    for ticker in DEFAULT_WATCHLIST:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), DEFAULT_USER, ticker, _now()),
        )


def init_if_needed() -> None:
    """Open the connection, apply the schema, and seed defaults (idempotent)."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
        _conn.executescript(_SCHEMA.read_text())
        _seed(_conn)
        _conn.commit()


def _require_conn() -> sqlite3.Connection:
    if _conn is None:
        init_if_needed()
    assert _conn is not None
    return _conn


def reset_for_tests() -> None:
    """Close and drop the shared connection so a new DB path takes effect."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


# --- Watchlist ---------------------------------------------------------------

def watchlist_tickers() -> list[str]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id=? ORDER BY added_at, rowid",
            (DEFAULT_USER,),
        ).fetchall()
    return [r["ticker"].upper() for r in rows]


def list_watchlist() -> list[dict]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id=? "
            "ORDER BY added_at, rowid",
            (DEFAULT_USER,),
        ).fetchall()
    return [{"ticker": r["ticker"], "added_at": r["added_at"]} for r in rows]


def add_watchlist(ticker: str) -> dict:
    """Add a ticker (idempotent). Returns the existing/new row. Provider
    ``is_supported`` validation is the caller's responsibility, not this layer's."""
    ticker = ticker.upper()
    conn = _require_conn()
    with _lock:
        existing = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id=? AND ticker=?",
            (DEFAULT_USER, ticker),
        ).fetchone()
        if existing:
            return {"ticker": existing["ticker"], "added_at": existing["added_at"]}
        added_at = _now()
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), DEFAULT_USER, ticker, added_at),
        )
        conn.commit()
    return {"ticker": ticker, "added_at": added_at}


def remove_watchlist(ticker: str) -> bool:
    ticker = ticker.upper()
    conn = _require_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE user_id=? AND ticker=?",
            (DEFAULT_USER, ticker),
        )
        conn.commit()
        return cur.rowcount > 0


# --- Positions ---------------------------------------------------------------

def _row_to_position(r: sqlite3.Row) -> dict:
    return {
        "ticker": r["ticker"],
        "quantity": r["quantity"],
        "avg_cost": r["avg_cost"],
        "updated_at": r["updated_at"],
    }


def position_tickers() -> list[str]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT ticker FROM positions WHERE user_id=? AND quantity>0",
            (DEFAULT_USER,),
        ).fetchall()
    return [r["ticker"].upper() for r in rows]


def list_positions() -> list[dict]:
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id=? ORDER BY ticker",
            (DEFAULT_USER,),
        ).fetchall()
    return [_row_to_position(r) for r in rows]


def get_position(ticker: str) -> dict | None:
    ticker = ticker.upper()
    conn = _require_conn()
    with _lock:
        r = conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id=? AND ticker=?",
            (DEFAULT_USER, ticker),
        ).fetchone()
    return _row_to_position(r) if r else None


# --- Cash --------------------------------------------------------------------

def get_cash() -> float:
    conn = _require_conn()
    with _lock:
        r = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id=?",
            (DEFAULT_USER,),
        ).fetchone()
    return r["cash_balance"] if r else 0.0


# --- Snapshots ---------------------------------------------------------------

def record_snapshot(total_value: float) -> None:
    """Append a portfolio-value snapshot (used by the 30s background task)."""
    conn = _require_conn()
    with _lock:
        _insert_snapshot(conn, total_value)
        conn.commit()


def _insert_snapshot(conn: sqlite3.Connection, total_value: float) -> None:
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), DEFAULT_USER, total_value, _now()),
    )


# --- Trades (PLAN.md §7) -----------------------------------------------------

def execute_trade(ticker: str, side: str, quantity: float, price: float) -> dict:
    """Execute a market order with PLAN §7 semantics, atomically.

    Buy: deduct cash, weighted-average the avg_cost. Sell: add cash, leave
    avg_cost unchanged, delete the row at quantity 0. Rejected (without
    raising) on insufficient cash/shares or invalid input — returns
    ``{"ok": False, "reason": ...}``. On success appends a trade row and a
    portfolio snapshot, and returns the trade, new cash, and resulting position.
    """
    ticker = ticker.upper()
    side = side.lower()
    if side not in ("buy", "sell"):
        return {"ok": False, "reason": f"invalid side: {side}"}
    if quantity <= 0:
        return {"ok": False, "reason": "quantity must be positive"}
    if price <= 0:
        return {"ok": False, "reason": "price must be positive"}

    conn = _require_conn()
    with _lock:
        cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id=?",
            (DEFAULT_USER,),
        ).fetchone()["cash_balance"]
        pos = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id=? AND ticker=?",
            (DEFAULT_USER, ticker),
        ).fetchone()
        cost = quantity * price

        if side == "buy":
            if cost > cash:
                return {"ok": False, "reason": "insufficient cash"}
            new_cash = cash - cost
            if pos:
                old_qty, old_cost = pos["quantity"], pos["avg_cost"]
                new_qty = old_qty + quantity
                new_avg = (old_qty * old_cost + quantity * price) / new_qty
            else:
                new_qty, new_avg = quantity, price
            position = _upsert_position(conn, ticker, new_qty, new_avg)
        else:  # sell
            held = pos["quantity"] if pos else 0.0
            if quantity > held:
                return {"ok": False, "reason": "insufficient shares"}
            new_cash = cash + cost
            new_qty = held - quantity
            if new_qty <= 0:
                conn.execute(
                    "DELETE FROM positions WHERE user_id=? AND ticker=?",
                    (DEFAULT_USER, ticker),
                )
                position = None
            else:
                position = _upsert_position(conn, ticker, new_qty, pos["avg_cost"])

        conn.execute(
            "UPDATE users_profile SET cash_balance=? WHERE id=?",
            (new_cash, DEFAULT_USER),
        )
        trade = _insert_trade(conn, ticker, side, quantity, price)
        _insert_snapshot(conn, _portfolio_value(conn))
        conn.commit()

    return {"ok": True, "trade": trade, "cash_balance": new_cash, "position": position}


def _upsert_position(
    conn: sqlite3.Connection, ticker: str, quantity: float, avg_cost: float
) -> dict:
    updated_at = _now()
    conn.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, ticker) DO UPDATE SET "
        "quantity=excluded.quantity, avg_cost=excluded.avg_cost, "
        "updated_at=excluded.updated_at",
        (str(uuid.uuid4()), DEFAULT_USER, ticker, quantity, avg_cost, updated_at),
    )
    return {
        "ticker": ticker,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "updated_at": updated_at,
    }


def _insert_trade(
    conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float
) -> dict:
    trade_id = str(uuid.uuid4())
    executed_at = _now()
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade_id, DEFAULT_USER, ticker, side, quantity, price, executed_at),
    )
    return {
        "id": trade_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": executed_at,
    }


def _portfolio_value(conn: sqlite3.Connection) -> float:
    """Cash + cost-basis of holdings. Live prices live in the market cache,
    not the DB, so trade-time snapshots use avg_cost as the position value;
    the 30s task passes a market-priced total to ``record_snapshot``."""
    cash = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id=?", (DEFAULT_USER,)
    ).fetchone()["cash_balance"]
    rows = conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id=?", (DEFAULT_USER,)
    ).fetchall()
    return cash + sum(r["quantity"] * r["avg_cost"] for r in rows)


# --- Chat messages -----------------------------------------------------------

def append_chat(role: str, content: str, actions: dict | list | None = None) -> dict:
    conn = _require_conn()
    msg_id = str(uuid.uuid4())
    created_at = _now()
    actions_json = json.dumps(actions) if actions is not None else None
    with _lock:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, DEFAULT_USER, role, content, actions_json, created_at),
        )
        conn.commit()
    return {
        "id": msg_id,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": created_at,
    }


def recent_chat(limit: int = 20) -> list[dict]:
    """Return up to ``limit`` most recent messages in chronological order."""
    conn = _require_conn()
    with _lock:
        rows = conn.execute(
            "SELECT id, role, content, actions, created_at FROM chat_messages "
            "WHERE user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (DEFAULT_USER, limit),
        ).fetchall()
    rows = list(reversed(rows))
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "actions": json.loads(r["actions"]) if r["actions"] is not None else None,
            "created_at": r["created_at"],
        }
        for r in rows
    ]
