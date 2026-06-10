"""Chat route (PLAN.md §8, §9).

POST /api/chat: send a message, get a complete JSON response (assistant text +
executed actions). No token streaming — Cerebras is fast enough that a single
response with a loading indicator is sufficient.

The heavy lifting (context build, LLM call, auto-execution, persistence) lives in
llm.executor; this route just wires in the live cache, the provider's
`is_supported`, the shared `execute_trade` path, and `recompute_tracked`. The
blocking DB/LLM work runs in a thread so the event loop stays responsive."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from tracking import recompute_tracked
from llm import executor
from api.execution import TradeError, execute_trade
from api.schemas import ChatRequest, ChatResponseModel, ExecutedAction

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(body: ChatRequest, request: Request) -> ChatResponseModel:
    app = request.app
    cache = app.state.cache
    provider = app.state.provider

    message, actions = await executor.run_chat(
        body.message.strip(),
        cache=cache,
        execute_trade=execute_trade,
        trade_error=TradeError,
        is_supported=provider.is_supported,
        on_change=lambda: recompute_tracked(app),
    )
    return ChatResponseModel(
        message=message,
        actions=[ExecutedAction(**a) for a in actions],
    )
