import { test, expect } from "@playwright/test";
import { sel } from "../support/selectors";
import { resetState, getWatchlist } from "../support/api";

/**
 * Watchlist add/remove and unknown-ticker rejection (PLAN.md §12, §8).
 * In simulator mode (default for tests) the supported universe is the seed
 * set; a symbol outside it must be rejected and not added.
 */

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("add a supported ticker via the UI", async ({ page, request }) => {
  await page.goto("/");
  // PYPL is a supported non-default extra in the simulator universe (seed.py).
  const ticker = "PYPL";

  await page.locator(sel.watchlistAddInput).fill(ticker);
  await page.locator(sel.watchlistAddButton).click();

  await expect(page.locator(sel.watchlistRow(ticker))).toBeVisible();
  const wl = await getWatchlist(request);
  expect(wl.map((w) => w.ticker.toUpperCase())).toContain(ticker);
});

test("remove a ticker via the UI", async ({ page, request }) => {
  await page.goto("/");
  const ticker = "NFLX";
  const row = page.locator(sel.watchlistRow(ticker));
  await expect(row).toBeVisible();

  // Hover reveals the remove button (opacity-0 until group-hover); clicking via
  // its testid works regardless, but hover keeps it deterministic.
  await row.hover();
  await page.locator(sel.watchlistRemove(ticker)).click();

  await expect(row).toHaveCount(0);
  const wl = await getWatchlist(request);
  expect(wl.map((w) => w.ticker.toUpperCase())).not.toContain(ticker);
});

test("reject an unknown ticker - error shown, not added", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const bogus = "ZZZZZ";

  const before = (await getWatchlist(request)).length;

  await page.locator(sel.watchlistAddInput).fill(bogus);
  await page.locator(sel.watchlistAddButton).click();

  // An inline error surfaces and the ticker is NOT added.
  await expect(page.locator(sel.watchlistError)).toBeVisible();
  await expect(page.locator(sel.watchlistRow(bogus))).toHaveCount(0);

  const wl = await getWatchlist(request);
  expect(wl.length).toBe(before);
  expect(wl.map((w) => w.ticker.toUpperCase())).not.toContain(bogus);
});

test("API rejects unknown ticker with a 400", async ({ request }) => {
  const res = await request.post("/api/watchlist", {
    data: { ticker: "ZZZZZ" },
  });
  expect(res.status(), "unknown ticker should be a client error").toBe(400);
});
