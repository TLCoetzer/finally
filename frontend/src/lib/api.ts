// Same-origin REST client for /api/* (PLAN.md §8). No CORS, no base URL.
import type {
  ChatResponse,
  HealthResponse,
  PortfolioResponse,
  TradeRequest,
  TradeResponse,
  WatchlistItem,
  WatchlistResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  getPortfolio: () => request<PortfolioResponse>("/api/portfolio"),

  trade: (body: TradeRequest) =>
    request<TradeResponse>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getWatchlist: () => request<WatchlistResponse>("/api/watchlist"),

  addWatchlist: (ticker: string) =>
    request<WatchlistItem>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),

  removeWatchlist: (ticker: string) =>
    request<void>(`/api/watchlist/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    }),

  chat: (message: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
