"""LLM client: call gpt-oss-120b via LiteLLM/OpenRouter with Cerebras (PLAN.md §9).

Uses the cerebras-inference pattern: model `openrouter/openai/gpt-oss-120b`,
`extra_body` pinning the Cerebras provider, and Structured Outputs via
`response_format=ChatResponse`. When `LLM_MOCK=true`, returns a deterministic
mock instead of calling the network (no API key required).

OPENROUTER_API_KEY is read from the environment; the project root `.env` is
loaded by python-dotenv on import so local runs pick it up automatically.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from .mock import mock_response
from .parser import parse_response
from .prompt import ChatTurn, PortfolioContext, build_messages
from .schema import ChatResponse

load_dotenv()  # project-root .env -> OPENROUTER_API_KEY, LLM_MOCK

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


def mock_enabled() -> bool:
    return os.getenv("LLM_MOCK", "").strip().lower() == "true"


def generate(
    ctx: PortfolioContext,
    history: list[ChatTurn],
    user_message: str,
) -> ChatResponse:
    """Produce a ChatResponse for the user's message.

    Mock mode short-circuits the network. Otherwise we call the model with
    structured outputs and parse defensively; any model/transport error degrades
    to a plain-message ChatResponse so the chat flow never hard-fails."""
    if mock_enabled():
        return mock_response(user_message)

    messages = build_messages(ctx, history, user_message)
    try:
        raw = _complete(messages)
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the request
        return ChatResponse(
            message=f"The assistant is temporarily unavailable ({type(exc).__name__})."
        )
    return parse_response(raw)


def _complete(messages: list[dict[str, str]]) -> str | None:
    """Single LiteLLM call. Imported lazily so the module (and its pure helpers)
    stays importable without litellm installed (e.g. in mock-only test runs)."""
    from litellm import completion

    response = completion(
        model=MODEL,
        messages=messages,
        response_format=ChatResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    return response.choices[0].message.content
