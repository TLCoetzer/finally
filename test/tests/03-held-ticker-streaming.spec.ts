import { test, expect } from "@playwright/test";
import { sel } from "../support/selectors";
import {
  resetState,
  trade,
  removeWatch,
  getPortfolio,
} from "../support/api";

/**
 * Held ticker keeps streaming after watchlist removal, with live P&L
 * (PLAN.md §12, §6 design decision 3). The tracked universe is
 * watchlist ∪ open positions, so a held-but-unwatched ticker still has a
 * cache entry, still streams, and keeps live unrealized P&L.
 */

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("held ticker streams and keeps live P&L after watchlist removal", async ({
  page,
  request,
}) => {
  const ticker = "AAPL";

  // Buy a position, then remove the ticker from the watchlist via the API.
  const buy = await trade(request, { ticker, quantity: 5, side: "buy" });
  expect(buy.ok(), `buy -> ${buy.status()}`).toBeTruthy();
  const rm = await removeWatch(request, ticker);
  expect(rm.ok(), `remove watch -> ${rm.status()}`).toBeTruthy();

  await page.goto("/");

  // No longer in the watchlist...
  await expect(page.locator(sel.watchlistRow(ticker))).toHaveCount(0);
  // ...but still a position row with a live P&L cell.
  const posRow = page.locator(sel.positionRow(ticker));
  await expect(posRow).toBeVisible();

  const pnlCell = page.locator(sel.positionPnl(ticker));
  await expect(pnlCell).toBeVisible();
  await expect(pnlCell).not.toHaveText("");

  // The "Last" (current price) column is the 4th <td> in the row. Confirm it
  // renders a positive number - the held ticker is still streaming.
  const lastCell = posRow.locator("td").nth(3);
  await expect
    .poll(
      async () => {
        const txt = (await lastCell.textContent()) ?? "";
        const num = Number(txt.replace(/[^0-9.]/g, ""));
        return Number.isFinite(num) && num > 0;
      },
      { timeout: 10_000 },
    )
    .toBe(true);

  // Server-side P&L stays live: portfolio reports a current price for AAPL.
  await expect
    .poll(
      async () => {
        const pf = await getPortfolio(request);
        const p = pf.positions.find((x) => x.ticker.toUpperCase() === ticker);
        return p && p.price ? p.price > 0 : false;
      },
      { timeout: 10_000 },
    )
    .toBe(true);
});
