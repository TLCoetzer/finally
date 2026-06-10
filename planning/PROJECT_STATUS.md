# FinAlly — Project Status

Last updated: 2026-06-10. Branch: `agent-teams`.

This logs what is built, how it was verified, and what remains, so work can resume
without re-deriving context. The master spec is `PLAN.md`; the market-data subsystem
is summarized in `MARKET_DATA_SUMMARY.md`.

## Build status: feature-complete

The platform was built by an agent team on top of the pre-existing (frozen)
market-data subsystem. All planned workstreams are delivered and tested.

| Area | Status | Key files |
|---|---|---|
| Market data (pre-existing) | Complete, frozen | `backend/market/`, `backend/api/stream.py`, `backend/tracking.py` |
| Database layer | Complete | `backend/db.py`, `backend/db/schema.sql` |
| Backend API routes | Complete | `backend/api/{portfolio,watchlist,health,snapshots,static,execution,schemas}.py`, `backend/app.py` |
| LLM chat | Complete | `backend/llm/`, `backend/api/chat.py` |
| Frontend | Complete | `frontend/` (Next.js static export) |
| DevOps | Complete | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `scripts/` |
| E2E tests | Complete (functional) | `test/` |

## Verification

- Backend unit tests: ~220 passing — `cd backend && uv run --python 3.12 --extra dev pytest -q`
- Frontend unit tests: 44 passing — `cd frontend && npm test`
- E2E (Playwright): 21/21 passing against the real running stack (FastAPI serving
  `/api/*` + the static frontend, `LLM_MOCK=true`, simulator). Covers every PLAN §12
  scenario including the AI-chat flow and SSE reconnect.
- Docker image: multi-stage build smoke-verified manually — `GET /` serves the SPA;
  `/api/health`, `/api/portfolio`, `/api/watchlist` return 200; `/api/stream/prices`
  streams live SSE; DB persists to the `/app/db` named volume.

## Architecture notes worth remembering

- Single shared trade-execution path: `backend/api/execution.py`
  (`execute_trade(cache, ticker, side, quantity)`). Both `POST /api/portfolio/trade`
  and the LLM chat auto-execution call it — there is no duplicated trade logic.
- After any trade or watchlist mutation, call `recompute_tracked(app)` so the cache
  streams the `watchlist ∪ positions` union (held-but-unwatched tickers keep live P&L).
- DB path is env-configurable: `FINALLY_DB_PATH` (default `db/finally.db` locally,
  `/app/db/finally.db` in Docker). WAL mode, single-writer via one lock; async callers
  use `asyncio.to_thread`.
- LLM: LiteLLM → OpenRouter `openrouter/openai/gpt-oss-120b`, Cerebras provider,
  Structured Outputs. `LLM_MOCK=true` short-circuits the network for tests/dev.

## Contract deviation from PLAN.md (intentional, implemented consistently)

PLAN.md §9 specified the chat response as `{message, trades[], watchlist_changes[]}`.
The actual implementation returns a **flat actions list**:
`{message, actions: [{kind, ok, summary, detail}]}`. Backend, frontend, and the E2E
selectors are all aligned to this real shape. If PLAN.md §9 is treated as canonical,
update it to match — the code is the source of truth here.

## Outstanding items

1. **Containerized E2E run not yet executed green (environment blocker).**
   The functional suite passes 21/21 against the real stack, but the canonical
   container wrapper did not complete because Docker Desktop's Linux engine crashed
   mid-build (needs an admin restart — not a code/test defect). To validate once
   Docker is healthy, from `test/`:
   ```
   docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from e2e
   ```
   Expect exit 0 / 21 passed. The runner pins Playwright 1.60.0 to match its base image.

2. **`/api/portfolio/history` + P&L chart — deferred by design** (PLAN.md §13 Open Item).
   Not built, pending a retention/downsampling policy decision. No frontend P&L chart.

3. **PLAN.md §9 schema** should be reconciled with the implemented flat `actions` shape
   (see "Contract deviation" above) if the doc is to stay authoritative.

## Running locally (non-Docker)

```
# Backend (from backend/)
uv run --python 3.12 uvicorn app:app --port 8000
# Frontend (from frontend/) — dev server, or `npm run build` for the static export
npm run dev
```

Set `OPENROUTER_API_KEY` in a root `.env` for live chat, or `LLM_MOCK=true` to mock it.
Leave `MASSIVE_API_KEY` empty to use the simulator.
