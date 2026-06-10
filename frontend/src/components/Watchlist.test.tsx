import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Watchlist } from "./Watchlist";

function setup(overrides: Partial<React.ComponentProps<typeof Watchlist>> = {}) {
  const props = {
    tickers: ["AAPL", "MSFT"],
    quotes: {},
    history: {},
    selected: "AAPL",
    onSelect: vi.fn(),
    onAdd: vi.fn().mockResolvedValue(undefined),
    onRemove: vi.fn(),
    ...overrides,
  };
  render(<Watchlist {...props} />);
  return props;
}

describe("Watchlist", () => {
  it("renders a row per ticker", () => {
    setup();
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-MSFT")).toBeInTheDocument();
  });

  it("adds a ticker and clears the input on success", async () => {
    const onAdd = vi.fn().mockResolvedValue(undefined);
    setup({ onAdd });
    const input = screen.getByTestId("watchlist-add-input") as HTMLInputElement;
    await userEvent.type(input, "pypl");
    fireEvent.click(screen.getByTestId("watchlist-add-button"));
    await waitFor(() => expect(onAdd).toHaveBeenCalledWith("PYPL"));
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("surfaces a rejection error from onAdd and keeps the input", async () => {
    const onAdd = vi.fn().mockRejectedValue(new Error("Ticker not supported: ZZZZ"));
    setup({ onAdd });
    const input = screen.getByTestId("watchlist-add-input") as HTMLInputElement;
    await userEvent.type(input, "ZZZZ");
    fireEvent.click(screen.getByTestId("watchlist-add-button"));
    await waitFor(() =>
      expect(screen.getByTestId("watchlist-error")).toHaveTextContent(
        "Ticker not supported: ZZZZ",
      ),
    );
    expect(input.value).toBe("ZZZZ");
  });

  it("removes a ticker", () => {
    const onRemove = vi.fn();
    setup({ onRemove });
    fireEvent.click(screen.getByTestId("remove-MSFT"));
    expect(onRemove).toHaveBeenCalledWith("MSFT");
  });

  it("shows an empty state when there are no tickers", () => {
    setup({ tickers: [] });
    expect(screen.getByText(/no tickers/i)).toBeInTheDocument();
  });
});
