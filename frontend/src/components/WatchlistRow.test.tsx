import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WatchlistRow } from "./WatchlistRow";
import type { PriceFrame } from "@/lib/types";

function frame(price: number, prev: number, changePct: number): PriceFrame {
  return {
    ticker: "AAPL",
    price,
    prev_price: prev,
    reference_price: prev,
    timestamp: 1,
    direction: price >= prev ? "up" : "down",
    change_pct: changePct,
  };
}

function row(frameProp?: PriceFrame) {
  const onSelect = vi.fn();
  const onRemove = vi.fn();
  const utils = render(
    <table>
      <tbody>
        <WatchlistRow
          ticker="AAPL"
          frame={frameProp}
          history={[]}
          selected={false}
          onSelect={onSelect}
          onRemove={onRemove}
        />
      </tbody>
    </table>,
  );
  return { onSelect, onRemove, ...utils };
}

describe("WatchlistRow", () => {
  it("renders price and change %", () => {
    row(frame(190.42, 190, 1.5));
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("190.42");
    expect(screen.getByTestId("change-AAPL")).toHaveTextContent("+1.50%");
  });

  it("applies a flash-up class when the price rises", () => {
    const { rerender } = render(
      <table>
        <tbody>
          <WatchlistRow
            ticker="AAPL"
            frame={frame(100, 100, 0)}
            history={[]}
            selected={false}
            onSelect={vi.fn()}
            onRemove={vi.fn()}
          />
        </tbody>
      </table>,
    );
    const cell = screen.getByTestId("price-AAPL").parentElement!;
    expect(cell.className).not.toContain("animate-flash");

    rerender(
      <table>
        <tbody>
          <WatchlistRow
            ticker="AAPL"
            frame={frame(101, 100, 1)}
            history={[]}
            selected={false}
            onSelect={vi.fn()}
            onRemove={vi.fn()}
          />
        </tbody>
      </table>,
    );
    expect(cell.className).toContain("animate-flashup");
  });

  it("selects on click and removes via the button without selecting", () => {
    const { onSelect, onRemove } = row(frame(100, 100, 0));
    fireEvent.click(screen.getByTestId("watchlist-row-AAPL"));
    expect(onSelect).toHaveBeenCalledWith("AAPL");

    fireEvent.click(screen.getByTestId("remove-AAPL"));
    expect(onRemove).toHaveBeenCalledWith("AAPL");
    expect(onSelect).toHaveBeenCalledTimes(1); // remove click did not re-select
  });

  it("shows placeholders before the first quote", () => {
    row(undefined);
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("--");
  });
});
