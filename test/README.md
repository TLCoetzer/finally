# FinAlly E2E Tests

Playwright end-to-end suite covering the PLAN.md §12 scenarios. Runs against the
full app (FastAPI API + static frontend on port 8000) with `LLM_MOCK=true` and
the built-in market simulator for determinism.

## Run in Docker (recommended)

From `test/`:

```bash
docker compose -f docker-compose.test.yml up --build \
    --abort-on-container-exit --exit-code-from e2e
```

This builds the production image (`../Dockerfile`), starts it with mock LLM and
the simulator on a fresh DB, waits for `/api/health`, then runs the suite. The
compose exit code is the suite result. The HTML report lands in
`test/playwright-report/`.

## Run locally against a running app

Start the app (e.g. `LLM_MOCK=true uv run uvicorn app:app --port 8000` from
`backend/`), then:

```bash
cd test
npm install
npx playwright install --with-deps chromium
npx playwright test            # BASE_URL defaults to http://localhost:8000
```

## Scenarios (`tests/`)

| Spec | Covers |
|---|---|
| `01-fresh-start` | default watchlist, $10k cash, streaming prices, connection dot |
| `02-watchlist` | add/remove ticker, reject unknown ticker |
| `03-held-ticker-streaming` | held-but-unwatched ticker keeps streaming + live P&L |
| `04-buy` | buy reduces cash, position + heatmap tile appear |
| `05-sell` | partial sell, full sell removes the row, oversell rejected |
| `06-portfolio-viz` | heatmap tiles + colors, positions table columns (P&L chart deferred) |
| `07-ai-chat` | mocked chat: send→response→inline auto-executed trade |
| `08-sse-resilience` | network drop → reconnect, prices resume |

## Selector contract

All UI locators live in `support/selectors.ts` (data-testid based). It is the
single point of coordination with the frontend; update only that file if the
frontend's testids change.
