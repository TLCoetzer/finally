"""Parser tests: valid structured output and graceful malformed handling."""
from __future__ import annotations

from llm.parser import parse_response
from llm.schema import Side, WatchlistAction


def test_parses_minimal_valid_response():
    r = parse_response('{"message": "hello"}')
    assert r.message == "hello"
    assert r.trades == []
    assert r.watchlist_changes == []


def test_parses_full_response_with_trades_and_watchlist():
    raw = (
        '{"message": "Done.",'
        ' "trades": [{"ticker": "aapl", "side": "buy", "quantity": 10}],'
        ' "watchlist_changes": [{"ticker": "pypl", "action": "add"}]}'
    )
    r = parse_response(raw)
    assert r.message == "Done."
    assert len(r.trades) == 1
    assert r.trades[0].ticker == "AAPL"  # normalized upper
    assert r.trades[0].side is Side.BUY
    assert r.trades[0].quantity == 10
    assert r.watchlist_changes[0].ticker == "PYPL"
    assert r.watchlist_changes[0].action is WatchlistAction.ADD


def test_strips_json_code_fence():
    raw = '```json\n{"message": "fenced"}\n```'
    assert parse_response(raw).message == "fenced"


def test_strips_bare_code_fence():
    raw = '```\n{"message": "bare"}\n```'
    assert parse_response(raw).message == "bare"


def test_extracts_json_embedded_in_prose():
    raw = 'Sure! Here you go: {"message": "embedded"} hope that helps'
    assert parse_response(raw).message == "embedded"


def test_non_json_text_becomes_message():
    raw = "I cannot do that, but here is some advice."
    assert parse_response(raw).message == raw
    assert parse_response(raw).trades == []


def test_none_and_empty_degrade_to_fallback():
    assert "trouble" in parse_response(None).message.lower()
    assert "trouble" in parse_response("   ").message.lower()


def test_valid_json_missing_message_salvages_or_falls_back():
    # JSON without the required `message`: no message to salvage -> treated as
    # plain text (the raw JSON becomes the message), never raises.
    r = parse_response('{"trades": []}')
    assert isinstance(r.message, str) and r.message
    assert r.trades == []


def test_wrong_shape_with_message_field_is_salvaged():
    # `trades` has the wrong type so schema validation fails, but a usable
    # `message` is present and should be lifted.
    raw = '{"message": "partial", "trades": "not-a-list"}'
    r = parse_response(raw)
    assert r.message == "partial"
    assert r.trades == []


def test_invalid_trade_quantity_rejected_then_salvaged_message():
    raw = '{"message": "bad qty", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 0}]}'
    r = parse_response(raw)
    # quantity must be > 0; schema fails, message salvaged.
    assert r.message == "bad qty"
    assert r.trades == []
