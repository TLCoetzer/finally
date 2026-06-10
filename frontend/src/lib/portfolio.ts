// Live portfolio math computed on the client from streamed prices (PLAN.md §10).
// /api/portfolio is authoritative on load; the header total updates live from SSE.
import type { PriceFrame, PositionItem } from "./types";

export interface LivePosition extends PositionItem {
  livePrice: number;
  liveValue: number;
  livePnl: number;
  livePnlPct: number; // vs avg_cost
}

// Resolve the current price for a position: prefer the live SSE quote, fall
// back to the snapshot price, then to avg_cost so value never reads as zero.
function priceFor(
  pos: PositionItem,
  quotes: Record<string, PriceFrame>,
): number {
  const q = quotes[pos.ticker];
  if (q && Number.isFinite(q.price)) return q.price;
  if (pos.price !== null && pos.price !== undefined) return pos.price;
  return pos.avg_cost;
}

export function livePositions(
  positions: PositionItem[],
  quotes: Record<string, PriceFrame>,
): LivePosition[] {
  return positions.map((pos) => {
    const livePrice = priceFor(pos, quotes);
    const liveValue = livePrice * pos.quantity;
    const livePnl = (livePrice - pos.avg_cost) * pos.quantity;
    const cost = pos.avg_cost * pos.quantity;
    const livePnlPct = cost !== 0 ? (livePnl / cost) * 100 : 0;
    return { ...pos, livePrice, liveValue, livePnl, livePnlPct };
  });
}

// Header total value: cash + live market value of every position.
export function liveTotalValue(
  cash: number,
  positions: PositionItem[],
  quotes: Record<string, PriceFrame>,
): number {
  const holdings = livePositions(positions, quotes).reduce(
    (sum, p) => sum + p.liveValue,
    0,
  );
  return cash + holdings;
}
