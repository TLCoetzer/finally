import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import db
from market.cache import PriceCache
from market.factory import create_provider
from tracking import recompute_tracked
from api import stream, portfolio, watchlist, health, chat
from api.snapshots import snapshot_loop
from api.static import mount_static

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_if_needed()              # lazy schema + seed (PLAN.md §7)
    cache = PriceCache()
    provider = create_provider(cache)
    app.state.cache = cache
    app.state.provider = provider
    recompute_tracked(app)           # watchlist ∪ positions (tracking.py)
    await provider.start()
    snapshot_task = asyncio.create_task(snapshot_loop(cache))  # 30s P&L snapshots
    try:
        yield
    finally:
        snapshot_task.cancel()
        await provider.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(stream.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(health.router)
app.include_router(chat.router)

# Mount the frontend export LAST so /api/* routers win; no-op if absent.
if not mount_static(app):
    logger.info("static dir absent; serving API only")
