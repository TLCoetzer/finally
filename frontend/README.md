# FinAlly Frontend

Next.js + TypeScript trading workstation, built as a **static export** and served
by the FastAPI backend (PLAN.md §3, §10). Talks to the backend over same-origin
`/api/*` and the `/api/stream/prices` SSE stream — no CORS, no base URL.

## Commands

```bash
npm install        # or `npm ci` with the committed package-lock.json
npm run dev        # local dev server (http://localhost:3000) — needs backend on /api
npm run build      # static export -> ./out  (index.html, 404.html, _next/...)
npm test           # vitest component/unit suite
```

The Dockerfile copies `frontend/out` into the image; the backend serves it.

## Structure

- `src/app/` — root layout (fonts, theme) and the single-page `page.tsx` that
  owns all state and wires the SSE stream to every panel.
- `src/components/` — Header, Watchlist, MainChart, Heatmap (treemap),
  PositionsTable, TradeBar, ChatPanel, and small parts (Sparkline, ConnectionDot).
- `src/lib/` — API client (`api.ts`), shared `types.ts` (mirrors the backend
  schemas), `usePriceStream` (the single EventSource), `useFlash` (price-flash),
  `portfolio.ts` (live client-side value/P&L), and formatters.

## Notes

- Charts and sparklines accumulate from the SSE stream since page load; there is
  no historical-price endpoint (PLAN.md §10).
- The header total value is computed live on the client from streamed prices;
  `/api/portfolio` is authoritative on load.
- The connection dot maps from `EventSource.readyState`
  (OPEN→green, CONNECTING→yellow, CLOSED→red).
- Stable `data-testid` selectors are present on every interactive element for E2E.
