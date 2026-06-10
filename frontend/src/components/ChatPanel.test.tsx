import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";
import type { ChatLine } from "@/lib/types";

const base = {
  lines: [] as ChatLine[],
  loading: false,
  collapsed: false,
  onToggle: vi.fn(),
  onSend: vi.fn(),
};

describe("ChatPanel", () => {
  it("renders user and assistant messages with action confirmations", () => {
    const lines: ChatLine[] = [
      { id: "1", role: "user", content: "Buy 5 AAPL" },
      {
        id: "2",
        role: "assistant",
        content: "Done.",
        actions: [
          { kind: "trade", ok: true, summary: "Bought 5 AAPL @ $190.00" },
          { kind: "watchlist", ok: true, summary: "Added PYPL to watchlist" },
        ],
      },
    ];
    render(<ChatPanel {...base} lines={lines} />);
    expect(screen.getByTestId("chat-line-user")).toHaveTextContent("Buy 5 AAPL");
    expect(screen.getByTestId("chat-line-assistant")).toHaveTextContent("Done.");
    expect(screen.getByTestId("chat-trade-confirm")).toHaveTextContent(
      "Bought 5 AAPL @ $190.00",
    );
    expect(screen.getByTestId("chat-watchlist-confirm")).toHaveTextContent(
      "Added PYPL to watchlist",
    );
  });

  it("renders a rejected action with its detail", () => {
    const lines: ChatLine[] = [
      {
        id: "2",
        role: "assistant",
        content: "Cannot.",
        actions: [
          {
            kind: "trade",
            ok: false,
            summary: "Buy 5 AAPL",
            detail: "insufficient cash",
          },
        ],
      },
    ];
    render(<ChatPanel {...base} lines={lines} />);
    const confirm = screen.getByTestId("chat-trade-confirm");
    expect(confirm).toHaveTextContent("insufficient cash");
    expect(confirm).toHaveAttribute("data-ok", "false");
  });

  it("shows the loading indicator while awaiting a response", () => {
    render(<ChatPanel {...base} loading />);
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
  });

  it("sends a message and does not send while loading", async () => {
    const onSend = vi.fn();
    const { rerender } = render(<ChatPanel {...base} onSend={onSend} />);
    await userEvent.type(screen.getByTestId("chat-input"), "hello");
    fireEvent.click(screen.getByTestId("chat-send"));
    await waitFor(() => expect(onSend).toHaveBeenCalledWith("hello"));

    onSend.mockClear();
    rerender(<ChatPanel {...base} onSend={onSend} loading />);
    // Send button is disabled while loading.
    expect(screen.getByTestId("chat-send")).toBeDisabled();
  });

  it("collapses to a toggle when collapsed", () => {
    render(<ChatPanel {...base} collapsed />);
    expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-toggle")).toBeInTheDocument();
  });
});
