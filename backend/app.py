from contextlib import asynccontextmanager

from fastapi import FastAPI

import db
from market.cache import PriceCache
from market.factory import create_provider
from tracking import recompute_tracked
from api import stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_if_needed()              # lazy schema + seed (PLAN.md §7)
    cache = PriceCache()
    provider = create_provider(cache)
    app.state.cache = cache
    app.state.provider = provider
    recompute_tracked(app)           # watchlist ∪ positions (tracking.py)
    await provider.start()
    try:
        yield
    finally:
        await provider.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(stream.router)
