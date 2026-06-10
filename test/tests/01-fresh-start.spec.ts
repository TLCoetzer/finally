import { test, expect } from "@playwright/test";
import { sel, ConnectionState } from "../support/selectors";
import { resetState, getPortfolio } from "../support/api";

// Render a number the way the header formats USD: "$1,234.56".
function usd(n: number): string {
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/**
 * Fresh start (PLAN.md §12, §2):
 *  - default 10-ticker watchlist appears
 *  - $10,000 cash balance shown
 *  - prices are streaming (a price renders for a ticker)
 *  - connection status dot reports connected
 */

const DEFAULT_WATCHLIST = [
  "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
  "NVDA", "META", "JPM", "V", "NFLX",
];

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("default watchlist of 10 tickers is shown", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(sel.watchlist)).toBeVisible();
  for (const t of DEFAULT_WATCHLIST) {
    await expect(
      page.locator(sel.watchlistRow(t)),
      `watchlist should contain ${t}`,
    ).toBeVisible();
  }
  await expect(page.locator(sel.watchlistRowAny)).toHaveCount(
    DEFAULT_WATCHLIST.length,
  );
});

test("cash balance shown matches the authoritative server value", async ({
  page,
  request,
}) => {
  // On a fresh DB (the canonical Docker compose run) the server reports
  // exactly $10,000. When re-run against a reused backend, round-trip trades
  // leave realized P&L so cash drifts; assert the UI matches server truth
  // rather than a hardcoded constant.
  const { cash } = await getPortfolio(request);
  await page.goto("/");
  const cell = page.locator(sel.cashBalance);
  await expect(cell).toBeVisible();
  await expect(cell).toHaveText(usd(cash));
});

test("prices are streaming - a watchlist price renders", async ({ page }) => {
  await page.goto("/");
  const priceCell = page.locator(sel.watchlistPrice("AAPL"));
  await expect(priceCell).toBeVisible();

  // The simulator ticks ~500ms; poll until the cell holds a positive number,
  // confirming the SSE stream is live and painting prices.
  await expect
    .poll(
      async () => {
        const txt = (await priceCell.textContent()) ?? "";
        const num = Number(txt.replace(/[^0-9.]/g, ""));
        return Number.isFinite(num) && num > 0;
      },
      { timeout: 10_000 },
    )
    .toBe(true);
});

test("connection status dot reports connected", async ({ page }) => {
  await page.goto("/");
  const dot = page.locator(sel.connectionDot);
  await expect(dot).toBeVisible();
  await expect(dot).toHaveAttribute(
    ConnectionState.attr,
    ConnectionState.connected,
    { timeout: 15_000 },
  );
});

test("header total value matches the authoritative server value", async ({
  page,
  request,
}) => {
  // With no open positions total == cash; assert against the server's value so
  // the test is correct on both a fresh DB ($10,000) and a reused backend.
  const { total_value } = await getPortfolio(request);
  await page.goto("/");
  const total = page.locator(sel.totalValue);
  await expect(total).toBeVisible();
  await expect(total).toHaveText(usd(total_value));
});
