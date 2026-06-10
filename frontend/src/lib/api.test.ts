import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

function mockFetch(body: unknown, init: { status?: number; ok?: boolean } = {}) {
  const status = init.status ?? 200;
  const ok = init.ok ?? status < 400;
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "ERR",
    json: async () => body,
  });
}

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("posts a trade to /api/portfolio/trade", async () => {
    const fetchMock = mockFetch({ ticker: "AAPL", side: "buy", quantity: 5, price: 190, executed_at: "x", cash: 100 });
    vi.stubGlobal("fetch", fetchMock);
    const res = await api.trade({ ticker: "AAPL", quantity: 5, side: "buy" });
    expect(res.cash).toBe(100);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/portfolio/trade");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ ticker: "AAPL", quantity: 5, side: "buy" });
  });

  it("throws ApiError with the backend detail on 400", async () => {
    vi.stubGlobal("fetch", mockFetch({ detail: "Ticker not supported: ZZZZ" }, { status: 400 }));
    await expect(api.addWatchlist("ZZZZ")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "Ticker not supported: ZZZZ",
    });
  });

  it("returns undefined for 204 No Content (delete)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.removeWatchlist("AAPL")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/watchlist/AAPL");
  });

  it("exports ApiError", () => {
    expect(new ApiError(500, "x")).toBeInstanceOf(Error);
  });
});
