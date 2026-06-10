import { test, expect } from "@playwright/test";
import { sel } from "../support/selectors";
import { resetState, trade, getPortfolio } from "../support/api";

/**
 * Sell shares (PLAN.md §12, §7):
 *  - partial sell: cash increases, position quantity decreases
 *  - full sell: position row is removed entirely (no zero-quantity rows)
 *
 * Qty is the 2nd <td> (index 1) of a position row.
 */

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("partial sell increases cash and reduces position quantity", async ({
  page,
  request,
}) => {
  const ticker = "AAPL";

  // Seed a 10-share position via the API, then sell 4 through the UI.
  const buy = await trade(request, { ticker, quantity: 10, side: "buy" });
  expect(buy.ok(), `seed buy -> ${buy.status()}`).toBeTruthy();

  await page.goto("/");
  await expect(page.locator(sel.positionRow(ticker))).toBeVisible();
  const before = await getPortfolio(request);

  await page.locator(sel.tradeTicker).fill(ticker);
  await page.locator(sel.tradeQuantity).fill("4");
  await page.locator(sel.tradeSell).click();

  const row = page.locator(sel.positionRow(ticker));
  await expect(row).toBeVisible();
  await expect(row.locator("td").nth(1)).toContainText("6");

  await expect
    .poll(async () => (await getPortfolio(request)).cash, { timeout: 10_000 })
    .toBeGreaterThan(before.cash);

  const after = await getPortfolio(request);
  const pos = after.positions.find((p) => p.ticker.toUpperCase() === ticker);
  expect(pos!.quantity).toBe(6);
});

test("full sell removes the position row entirely", async ({
  page,
  request,
}) => {
  const ticker = "TSLA";

  const buy = await trade(request, { ticker, quantity: 5, side: "buy" });
  expect(buy.ok(), `seed buy -> ${buy.status()}`).toBeTruthy();

  await page.goto("/");
  await expect(page.locator(sel.positionRow(ticker))).toBeVisible();

  await page.locator(sel.tradeTicker).fill(ticker);
  await page.locator(sel.tradeQuantity).fill("5");
  await page.locator(sel.tradeSell).click();

  // Row disappears from the table (no zero-quantity rows kept).
  await expect(page.locator(sel.positionRow(ticker))).toHaveCount(0);

  // And the position row is gone server-side too.
  const after = await getPortfolio(request);
  expect(
    after.positions.some((p) => p.ticker.toUpperCase() === ticker),
  ).toBe(false);
});

test("selling more than held is rejected by the API", async ({ request }) => {
  const ticker = "JPM";
  const buy = await trade(request, { ticker, quantity: 2, side: "buy" });
  expect(buy.ok()).toBeTruthy();

  const res = await trade(request, { ticker, quantity: 99, side: "sell" });
  expect(res.status(), "oversell should be a client error").toBe(400);
});
