from __future__ import annotations
import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from market.cache import PriceCache
from market.sse import quote_to_sse
from api.deps import get_cache

router = APIRouter()

SSE_INTERVAL = 0.5      # ~500ms cadence (PLAN.md §6, §10)
HEARTBEAT_EVERY = 30.0  # comment ping to keep proxies from closing idle conns


async def _price_event_gen(request: Request, cache: PriceCache):
    """Yield SSE frames for every cached ticker every ~500ms.

    Flushes the current snapshot immediately on connect so the client paints
    without waiting a full interval. Sends a heartbeat comment every 30s to
    prevent proxy/load-balancer timeouts on idle connections."""
    last_beat = 0.0
    first = True
    while True:
        if await request.is_disconnected():
            break
        for q in cache.all().values():
            yield quote_to_sse(q)
        last_beat += SSE_INTERVAL
        if first or last_beat >= HEARTBEAT_EVERY:
            yield ": ping\n\n"
            last_beat = 0.0
            first = False
        await asyncio.sleep(SSE_INTERVAL)


@router.get("/api/stream/prices")
async def stream_prices(
    request: Request,
    cache: PriceCache = Depends(get_cache),
) -> StreamingResponse:
    return StreamingResponse(
        _price_event_gen(request, cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )
