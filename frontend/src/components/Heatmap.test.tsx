import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Heatmap } from "./Heatmap";
import type { LivePosition } from "@/lib/portfolio";

const livePos = (over: Partial<LivePosition>): LivePosition => ({
  ticker: "AAPL",
  quantity: 10,
  avg_cost: 100,
  price: null,
  market_value: null,
  unrealized_pnl: null,
  change_pct: null,
  livePrice: 110,
  liveValue: 1100,
  livePnl: 100,
  livePnlPct: 10,
  ...over,
});

describe("Heatmap", () => {
  it("renders a tile per priced position colored by P&L sign", () => {
    render(
      <Heatmap
        positions={[
          livePos({ ticker: "AAPL", livePnlPct: 8 }),
          livePos({ ticker: "TSLA", liveValue: 500, livePnlPct: -6 }),
        ]}
      />,
    );
    const gain = screen.getByTestId("heatmap-cell-AAPL").querySelector("rect")!;
    const loss = screen.getByTestId("heatmap-cell-TSLA").querySelector("rect")!;
    expect(gain.getAttribute("fill")).toContain("27,196,125"); // green
    expect(loss.getAttribute("fill")).toContain("240,80,110"); // red
  });

  it("shows an empty state when there are no positions", () => {
    render(<Heatmap positions={[]} />);
    expect(screen.getByText(/no positions to map/i)).toBeInTheDocument();
  });
});
