import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Header } from "./Header";

describe("Header", () => {
  it("renders total value, cash, and source", () => {
    render(<Header totalValue={12345.6} cash={9000} source="simulator" conn="open" />);
    expect(screen.getByTestId("header-total-value")).toHaveTextContent("$12,345.60");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$9,000.00");
    expect(screen.getByTestId("market-source")).toHaveTextContent("simulator");
  });

  it("exposes the connection state on the dot", () => {
    const { rerender } = render(<Header totalValue={0} cash={0} conn="open" />);
    expect(screen.getByTestId("connection-dot")).toHaveAttribute("data-conn", "open");
    rerender(<Header totalValue={0} cash={0} conn="connecting" />);
    expect(screen.getByTestId("connection-dot")).toHaveAttribute("data-conn", "connecting");
    rerender(<Header totalValue={0} cash={0} conn="closed" />);
    expect(screen.getByTestId("connection-dot")).toHaveAttribute("data-conn", "closed");
  });
});
