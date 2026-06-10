import { test, expect } from "@playwright/test";
import { sel } from "../support/selectors";
import { resetState, trade } from "../support/api";

/**
 * Portfolio visualization (PLAN.md §12, §10):
 *  - heatmap renders a tile (SVG cell) per position, colored by P&L
 *  - positions table shows ticker, qty, avg cost, current price, P&L, %change
 *
 * The heatmap tile color is an rgba fill keyed by P&L sign (Heatmap.tsx):
 * green rgba(27,196,125,a) for >=0, red rgba(240,80,110,a) for <0. We assert
 * the tile renders and its rect fill is one of those families (no brittle
 * pixel sampling).
 *
 * NOTE: the P&L line chart is DEFERRED (PLAN.md §13 open item) and is
 * intentionally NOT tested here.
 */

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("heatmap renders a tile per position colored by P&L", async ({
  page,
  request,
}) => {
  await trade(request, { ticker: "AAPL", quantity: 4, side: "buy" });
  await trade(request, { ticker: "MSFT", quantity: 3, side: "buy" });

  await page.goto("/");
  await expect(page.locator(sel.heatmap)).toBeVisible();

  for (const t of ["AAPL", "MSFT"]) {
    const cell = page.locator(sel.heatmapCell(t));
    await expect(cell).toBeVisible();
    // Fill is a green (27,196,125) or red (240,80,110) rgba family.
    const fill = await cell.locator("rect").first().getAttribute("fill");
    expect(fill, `${t} tile fill`).toMatch(
      /rgba\((?:27,196,125|240,80,110),/,
    );
  }
});

test("positions table shows all required columns for a holding", async ({
  page,
  request,
}) => {
  await trade(request, { ticker: "NVDA", quantity: 5, side: "buy" });

  await page.goto("/");
  await expect(page.locator(sel.positionsTable)).toBeVisible();

  const row = page.locator(sel.positionRow("NVDA"));
  await expect(row).toBeVisible();

  // Columns: Sym(0) Qty(1) Avg(2) Last(3) P&L(4) %(5).
  await expect(row.locator("td").nth(0)).toContainText("NVDA");
  await expect(row.locator("td").nth(1)).toContainText("5");
  await expect(row.locator("td").nth(2)).not.toHaveText(""); // avg cost
  await expect(row.locator("td").nth(3)).not.toHaveText(""); // last price
  await expect(page.locator(sel.positionPnl("NVDA"))).not.toHaveText(""); // P&L
  await expect(row.locator("td").nth(5)).not.toHaveText(""); // % change
});
