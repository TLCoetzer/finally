import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TradeBar } from "./TradeBar";
import type { TradeResponse } from "@/lib/types";

const okTrade = (side: "buy" | "sell"): TradeResponse => ({
  ticker: "AAPL",
  side,
  quantity: 5,
  price: 190,
  executed_at: "2026-01-01T00:00:00Z",
  cash: 9050,
});

describe("TradeBar", () => {
  it("buys and shows a success message", async () => {
    const onTrade = vi.fn().mockResolvedValue(okTrade("buy"));
    render(<TradeBar onTrade={onTrade} />);
    await userEvent.type(screen.getByTestId("trade-ticker"), "AAPL");
    await userEvent.type(screen.getByTestId("trade-qty"), "5");
    fireEvent.click(screen.getByTestId("trade-buy"));
    await waitFor(() => expect(onTrade).toHaveBeenCalledWith("AAPL", 5, "buy"));
    expect(await screen.findByTestId("trade-message")).toHaveTextContent(
      "BUY 5 AAPL @ $190.00",
    );
  });

  it("validates ticker and positive quantity before trading", async () => {
    const onTrade = vi.fn();
    render(<TradeBar onTrade={onTrade} />);
    fireEvent.click(screen.getByTestId("trade-sell"));
    expect(await screen.findByTestId("trade-message")).toHaveTextContent(/positive quantity/i);
    expect(onTrade).not.toHaveBeenCalled();
  });

  it("surfaces a backend rejection", async () => {
    const onTrade = vi.fn().mockRejectedValue(new Error("Insufficient cash"));
    render(<TradeBar onTrade={onTrade} />);
    await userEvent.type(screen.getByTestId("trade-ticker"), "AAPL");
    await userEvent.type(screen.getByTestId("trade-qty"), "100000");
    fireEvent.click(screen.getByTestId("trade-buy"));
    expect(await screen.findByTestId("trade-message")).toHaveTextContent("Insufficient cash");
  });

  it("prefills the ticker from the selection", () => {
    render(<TradeBar selectedTicker="NVDA" onTrade={vi.fn()} />);
    expect(screen.getByTestId("trade-ticker")).toHaveValue("NVDA");
  });
});
