import { describe, expect, it } from "vitest";
import { livePositions, liveTotalValue } from "./portfolio";
import type { PositionItem, PriceFrame } from "./types";

function frame(ticker: string, price: number): PriceFrame {
  return {
    ticker,
    price,
    prev_price: price,
    reference_price: price,
    timestamp: 0,
    direction: "flat",
    change_pct: 0,
  };
}

const pos = (ticker: string, quantity: number, avg_cost: number): PositionItem => ({
  ticker,
  quantity,
  avg_cost,
  price: null,
  market_value: null,
  unrealized_pnl: null,
  change_pct: null,
});

describe("livePositions", () => {
  it("computes live value and P&L from streamed prices", () => {
    const positions = [pos("AAPL", 10, 100)];
    const quotes = { AAPL: frame("AAPL", 110) };
    const [p] = livePositions(positions, quotes);
    expect(p.livePrice).toBe(110);
    expect(p.liveValue).toBe(1100);
    expect(p.livePnl).toBe(100); // (110-100)*10
    expect(p.livePnlPct).toBeCloseTo(10); // vs avg_cost
  });

  it("shows a loss with negative P&L and pct", () => {
    const [p] = livePositions([pos("TSLA", 5, 200)], { TSLA: frame("TSLA", 180) });
    expect(p.livePnl).toBe(-100);
    expect(p.livePnlPct).toBeCloseTo(-10);
  });

  it("falls back to snapshot price then avg_cost when no live quote", () => {
    const snapshot: PositionItem = { ...pos("MSFT", 2, 300), price: 320 };
    const [withSnap] = livePositions([snapshot], {});
    expect(withSnap.livePrice).toBe(320);

    const [noPrice] = livePositions([pos("NVDA", 2, 500)], {});
    expect(noPrice.livePrice).toBe(500); // avg_cost fallback -> zero P&L
    expect(noPrice.livePnl).toBe(0);
  });
});

describe("liveTotalValue", () => {
  it("is cash plus live market value of all positions", () => {
    const positions = [pos("AAPL", 10, 100), pos("MSFT", 5, 200)];
    const quotes = { AAPL: frame("AAPL", 110), MSFT: frame("MSFT", 210) };
    // cash 1000 + 10*110 + 5*210 = 1000 + 1100 + 1050 = 3150
    expect(liveTotalValue(1000, positions, quotes)).toBe(3150);
  });

  it("equals cash when there are no positions", () => {
    expect(liveTotalValue(10000, [], {})).toBe(10000);
  });
});
