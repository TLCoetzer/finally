import { defineConfig, devices } from "@playwright/test";

/**
 * FinAlly E2E config (PLAN.md §12).
 *
 * BASE_URL points at the running app (API + static frontend on one origin,
 * port 8000). In docker-compose.test.yml the runner reaches the app service
 * at http://web:8000 (named "web", not "app", to avoid Chromium's HSTS
 * preload of the ".app" gTLD force-upgrading it to https); for local runs it
 * defaults to http://localhost:8000.
 */
const baseURL = process.env.BASE_URL ?? "http://localhost:8000";

export default defineConfig({
  testDir: "./tests",
  // Streaming/price-driven assertions need generous time; keep CI deterministic.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // Trades + DB writes share single-user state, so run serially to avoid
  // cross-test interference on the shared "default" portfolio.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
