import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PositionsTable } from "./PositionsTable";
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

describe("PositionsTable", () => {
  it("renders a row per position with P&L and qty", () => {
    render(
      <PositionsTable
        positions={[livePos({}), livePos({ ticker: "TSLA", livePnl: -50, livePnlPct: -5 })]}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByTestId("position-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("pnl-AAPL")).toHaveTextContent("+$100.00");
    expect(screen.getByTestId("pnl-TSLA")).toHaveTextContent("-$50.00");
  });

  it("selects a ticker on row click", () => {
    const onSelect = vi.fn();
    render(<PositionsTable positions={[livePos({})]} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("position-row-AAPL"));
    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });

  it("shows an empty state with no positions", () => {
    render(<PositionsTable positions={[]} onSelect={vi.fn()} />);
    expect(screen.getByText(/no open positions/i)).toBeInTheDocument();
  });
});
