import { test, expect, Page } from "@playwright/test";
import { sel } from "../support/selectors";
import { resetState, getPortfolio } from "../support/api";

/**
 * AI chat with LLM_MOCK=true (PLAN.md §9, §12):
 *  - send a message, receive an assistant response
 *  - a mock-triggered trade auto-executes and is shown inline as a confirmation
 *  - the trade is reflected in the portfolio (cash down, position created)
 *
 * The mock (backend/llm/mock.py) is keyed off the message: "buy" + an
 * all-caps ticker -> a single BUY trade of quantity 1 for that ticker.
 * "buy AAPL" therefore yields exactly one AAPL buy of qty 1.
 */

const TRIGGER = "buy AAPL";
const TRIGGER_QTY = 1;

test.beforeEach(async ({ request }) => {
  await resetState(request);
});

// The chat panel starts expanded, but open it defensively if collapsed.
async function ensureChatOpen(page: Page) {
  if (!(await page.locator(sel.chatPanel).isVisible())) {
    await page.locator(sel.chatToggle).click();
  }
  await expect(page.locator(sel.chatPanel)).toBeVisible();
}

test("chat send returns an assistant response", async ({ page }) => {
  await page.goto("/");
  await ensureChatOpen(page);

  await page.locator(sel.chatInput).fill("How is my portfolio doing?");
  await page.locator(sel.chatSend).click();

  // User message echoed, then an assistant reply lands.
  await expect(page.locator(sel.chatMessageUser).last()).toContainText(
    "How is my portfolio",
  );
  await expect(page.locator(sel.chatMessageAssistant).last()).toBeVisible();
  await expect(page.locator(sel.chatMessageAssistant).last()).not.toHaveText(
    "",
  );
});

test("mocked chat trade auto-executes and shows inline confirmation", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await ensureChatOpen(page);
  const before = await getPortfolio(request);

  await page.locator(sel.chatInput).fill(TRIGGER);
  await page.locator(sel.chatSend).click();

  // Assistant replies and an inline trade confirmation appears.
  await expect(page.locator(sel.chatMessageAssistant).last()).toBeVisible();
  await expect(page.locator(sel.chatTradeConfirm).last()).toBeVisible();
  await expect(page.locator(sel.chatTradeConfirm).last()).toContainText(
    /AAPL/i,
  );

  // The position appears and cash drops (auto-executed, no confirm dialog).
  await expect(page.locator(sel.positionRow("AAPL"))).toBeVisible();
  await expect
    .poll(async () => (await getPortfolio(request)).cash, { timeout: 10_000 })
    .toBeLessThan(before.cash);

  const after = await getPortfolio(request);
  const pos = after.positions.find((p) => p.ticker.toUpperCase() === "AAPL");
  expect(pos, "AAPL position should exist after mocked chat trade").toBeTruthy();
  expect(pos!.quantity).toBe(TRIGGER_QTY);
});

test("API: mocked chat returns structured message + actions", async ({
  request,
}) => {
  const res = await request.post("/api/chat", { data: { message: TRIGGER } });
  expect(res.ok(), `POST /api/chat -> ${res.status()}`).toBeTruthy();
  const body = await res.json();
  expect(typeof body.message).toBe("string");
  expect(body.message.length).toBeGreaterThan(0);
  expect(Array.isArray(body.actions)).toBe(true);
  expect(
    body.actions.some(
      (a: { kind: string; ok: boolean }) => a.kind === "trade" && a.ok,
    ),
    "a trade action should have auto-executed",
  ).toBe(true);
});
