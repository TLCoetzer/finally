import json

from .types import Quote


def quote_to_sse(q: Quote) -> str:
    """Serialize one Quote as an SSE 'message' event frame.

    Wire format (one frame):
        data: {"ticker": "AAPL", "price": 190.42, ...}\\n\\n
    """
    payload = {
        "ticker": q.ticker,
        "price": q.price,
        "prev_price": q.prev_price,
        "reference_price": q.reference_price,
        "timestamp": q.timestamp,
        "direction": q.direction.value,   # "up" | "down" | "flat"
        "change_pct": round(q.change_pct, 4),
    }
    return f"data: {json.dumps(payload)}\n\n"
