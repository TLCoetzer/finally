"""Parse the LLM's raw text into a ChatResponse, gracefully (PLAN.md §9, §12).

Structured outputs *should* yield clean JSON matching ChatResponse, but the
model can still emit malformed or code-fenced JSON, or omit required fields. We
never raise on bad model output: a parse failure degrades to a plain message so
the chat flow stays alive and the user always gets a reply.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from .schema import ChatResponse

_FALLBACK = (
    "I had trouble formatting my response. Please rephrase or try again."
)


def parse_response(raw: str | None) -> ChatResponse:
    """Best-effort parse of raw model output into a ChatResponse.

    Order of attempts:
      1. strict JSON -> ChatResponse
      2. strip ```json fences / surrounding prose, retry
    On total failure, return a ChatResponse whose `message` is the salvaged raw
    text (if any) or a generic fallback, with no trades/watchlist changes."""
    if raw is None:
        return ChatResponse(message=_FALLBACK)

    text = raw.strip()
    if not text:
        return ChatResponse(message=_FALLBACK)

    for candidate in _json_candidates(text):
        try:
            return ChatResponse.model_validate_json(candidate)
        except ValidationError:
            # Valid JSON but wrong shape (e.g. missing `message`): try to
            # salvage a message string before giving up on this candidate.
            salvaged = _salvage_message(candidate)
            if salvaged is not None:
                return ChatResponse(message=salvaged)
        except (json.JSONDecodeError, ValueError):
            continue

    # Not JSON at all — treat the whole thing as the assistant's message.
    return ChatResponse(message=text)


def _json_candidates(text: str):
    """Yield progressively-cleaned strings that might be valid JSON."""
    yield text

    fenced = _strip_code_fence(text)
    if fenced != text:
        yield fenced

    extracted = _extract_braces(text)
    if extracted is not None and extracted not in (text, fenced):
        yield extracted


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    body = text[3:]
    if body[:4].lower() == "json":
        body = body[4:]
    body = body.lstrip("\n")
    end = body.rfind("```")
    return body[:end].strip() if end != -1 else body.strip()


def _extract_braces(text: str) -> str | None:
    """Return the substring spanning the first '{' to the last '}', or None."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _salvage_message(candidate: str) -> str | None:
    """If JSON parses but fails the schema, try to lift a usable `message`."""
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        msg = data.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg
    return None
