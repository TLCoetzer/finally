import { APIRequestContext, expect } from "@playwright/test";

/**
 * Thin wrappers over the FinAlly REST API (PLAN.md §8). Used by tests for
 * setup/teardown and for asserting authoritative server state alongside the
 * UI. All endpoints are same-origin under /api.
 */

// Shapes mirror backend/api/schemas.py (PLAN.md §8).
export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  price?: number | null; // current price from cache (null until first tick)
  market_value?: number | null;
  unrealized_pnl?: number | null;
  change_pct?: number | null; // vs avg_cost
}

export interface Portfolio {
  cash: number;
  total_value: number;
  positions: Position[];
}

export interface WatchlistItem {
  ticker: string;
  price?: number | null;
  reference_price?: number | null;
  change_pct?: number | null;
  direction?: string | null;
}

export async function getPortfolio(api: APIRequestContext): Promise<Portfolio> {
  const res = await api.get("/api/portfolio");
  expect(res.ok(), `GET /api/portfolio -> ${res.status()}`).toBeTruthy();
  return res.json();
}

export async function getWatchlist(
  api: APIRequestContext,
): Promise<WatchlistItem[]> {
  const res = await api.get("/api/watchlist");
  expect(res.ok(), `GET /api/watchlist -> ${res.status()}`).toBeTruthy();
  const body = await res.json();
  return body.tickers as WatchlistItem[];
}

export async function trade(
  api: APIRequestContext,
  body: { ticker: string; quantity: number; side: "buy" | "sell" },
) {
  return api.post("/api/portfolio/trade", { data: body });
}

export async function addWatch(api: APIRequestContext, ticker: string) {
  return api.post("/api/watchlist", { data: { ticker } });
}

export async function removeWatch(api: APIRequestContext, ticker: string) {
  return api.delete(`/api/watchlist/${ticker}`);
}

/**
 * Reset the shared single-user ("default") state to a known baseline so each
 * spec starts deterministically: liquidate every position and restore the
 * default watchlist. There is no dedicated reset endpoint in the spec, so we
 * drive the public API.
 */
export async function resetState(api: APIRequestContext) {
  const portfolio = await getPortfolio(api);
  for (const p of portfolio.positions) {
    if (p.quantity > 0) {
      const res = await trade(api, {
        ticker: p.ticker,
        quantity: p.quantity,
        side: "sell",
      });
      expect(res.ok(), `liquidate ${p.ticker} -> ${res.status()}`).toBeTruthy();
    }
  }

  const DEFAULT_WATCHLIST = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
  ];
  const current = await getWatchlist(api);
  const have = new Set(current.map((w) => w.ticker.toUpperCase()));
  for (const w of current) {
    if (!DEFAULT_WATCHLIST.includes(w.ticker.toUpperCase())) {
      await removeWatch(api, w.ticker);
    }
  }
  for (const t of DEFAULT_WATCHLIST) {
    if (!have.has(t)) await addWatch(api, t);
  }
}

export async function waitForHealth(api: APIRequestContext, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const res = await api.get("/api/health");
      if (res.ok()) return;
      last = `status ${res.status()}`;
    } catch (e) {
      last = String(e);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`app /api/health not ready within ${timeoutMs}ms: ${last}`);
}
