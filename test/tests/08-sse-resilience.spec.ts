import { test, expect } from "@playwright/test";
import { sel, ConnectionState } from "../support/selectors";
import { resetState } from "../support/api";

/**
 * SSE resilience (PLAN.md §12, §10): EventSource auto-reconnects when the
 * stream is unavailable. We block the SSE endpoint so the EventSource cannot
 * connect - the dot must be non-"open" (CONNECTING→yellow as it retries) - then
 * unblock it so the native EventSource retry connects, driving the dot to
 * "open" and resuming live prices.
 *
 * Why block from the start rather than mid-stream: neither context.setOffline
 * nor CDP offline tears down an ALREADY-open streaming-fetch SSE socket
 * (verified), so the only reliable, deterministic disconnect is to fail the
 * connection itself and then allow the browser's built-in EventSource retry to
 * recover - which is exactly the reconnection path the frontend implements.
 */

const STREAM = "**/api/stream/prices";

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

test("EventSource reconnects when the stream recovers", async ({ page }) => {
  let block = true;
  await page.route(STREAM, async (route) => {
    if (block) await route.abort();
    else await route.fallback();
  });

  await page.goto("/");

  // Stream is unavailable: the dot reflects a non-connected state while the
  // EventSource retries (CONNECTING→yellow, or CLOSED→red).
  const dot = page.locator(sel.connectionDot);
  await expect
    .poll(async () => dot.getAttribute(ConnectionState.attr), {
      timeout: 15_000,
    })
    .not.toBe(ConnectionState.connected);

  // Recover the stream: the browser's EventSource auto-retry reconnects.
  block = false;
  await expect(dot).toHaveAttribute(
    ConnectionState.attr,
    ConnectionState.connected,
    { timeout: 20_000 },
  );

  // Prices resume streaming after reconnect.
  const priceCell = page.locator(sel.watchlistPrice("AAPL"));
  await expect(priceCell).toBeVisible();
  await expect
    .poll(
      async () => {
        const txt = (await priceCell.textContent()) ?? "";
        const num = Number(txt.replace(/[^0-9.]/g, ""));
        return Number.isFinite(num) && num > 0;
      },
      { timeout: 15_000 },
    )
    .toBe(true);
});
