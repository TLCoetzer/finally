import { test, expect } from "@playwright/test";
import { sel } from "../support/selectors";
import { resetState, getPortfolio } from "../support/api";

/**
 * Buy shares via the trade bar (PLAN.md §12, §2, §7):
 *  - cash decreases
 *  - a position appears in the positions table
 *  - the position also surfaces as a heatmap tile
 *
 * Positions table columns (PositionsTable.tsx): Sym, Qty, Avg, Last, P&L, %.
 * Only the row and the P&L cell carry testids; Qty is the 2nd <td> (index 1).
 */

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("buying shares reduces cash and creates a position", async ({
  page,
  request,
}) => {
  const ticker = "MSFT";
  const qty = 3;

  await page.goto("/");
  const before = await getPortfolio(request);

  await page.locator(sel.tradeTicker).fill(ticker);
  await page.locator(sel.tradeQuantity).fill(String(qty));
  await page.locator(sel.tradeBuy).click();

  // Position row appears with the bought quantity (Qty = 2nd cell).
  const row = page.locator(sel.positionRow(ticker));
  await expect(row).toBeVisible();
  await expect(row.locator("td").nth(1)).toContainText(String(qty));

  // Cash decreased (authoritative server check).
  await expect
    .poll(async () => (await getPortfolio(request)).cash, { timeout: 10_000 })
    .toBeLessThan(before.cash);

  const after = await getPortfolio(request);
  const pos = after.positions.find((p) => p.ticker.toUpperCase() === ticker);
  expect(pos, "position should exist after buy").toBeTruthy();
  expect(pos!.quantity).toBe(qty);
});

test("a bought position appears as a heatmap tile", async ({ page }) => {
  const ticker = "NVDA";
  await page.goto("/");

  await page.locator(sel.tradeTicker).fill(ticker);
  await page.locator(sel.tradeQuantity).fill("2");
  await page.locator(sel.tradeBuy).click();

  await expect(page.locator(sel.positionRow(ticker))).toBeVisible();
  await expect(page.locator(sel.heatmapCell(ticker))).toBeVisible();
});
