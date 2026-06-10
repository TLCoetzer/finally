// Shared types mirroring the backend contract (PLAN.md §6/§8, backend/api/schemas.py).

export type Direction = "up" | "down" | "flat";

// One SSE frame from GET /api/stream/prices (backend/market/sse.py).
export interface PriceFrame {
  ticker: string;
  price: number;
  prev_price: number;
  reference_price: number;
  timestamp: number;
  direction: Direction;
  change_pct: number; // vs reference_price
}

// GET /api/watchlist item.
export interface WatchlistItem {
  ticker: string;
  price: number | null;
  reference_price: number | null;
  change_pct: number | null;
  direction: string | null;
}

export interface WatchlistResponse {
  tickers: WatchlistItem[];
}

// GET /api/portfolio.
export interface PositionItem {
  ticker: string;
  quantity: number;
  avg_cost: number;
  price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  change_pct: number | null; // gain/loss vs avg_cost
}

export interface PortfolioResponse {
  cash: number;
  positions: PositionItem[];
  total_value: number;
}

// POST /api/portfolio/trade.
export type TradeSide = "buy" | "sell";

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: TradeSide;
}

export interface TradeResponse {
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  executed_at: string;
  cash: number;
}

// GET /api/health.
export interface HealthResponse {
  status: string;
  source: "simulator" | "massive";
}

// POST /api/chat (backend/api/schemas.py). The backend returns the assistant
// message plus a flat list of executed actions (trades + watchlist changes),
// each carrying its own outcome.
export interface ExecutedAction {
  kind: string; // "trade" | "watchlist"
  ok: boolean;
  summary: string; // human-readable, e.g. "Bought 10 AAPL @ $190.00"
  detail?: string | null; // rejection reason when ok is false
}

export interface ChatResponse {
  message: string;
  actions: ExecutedAction[];
}

// Local UI model: a chat line rendered in the panel.
export interface ChatLine {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions?: ExecutedAction[];
}

// A single accumulated price point for charts/sparklines.
export interface PricePoint {
  t: number; // ms epoch
  price: number;
}
