# Massive API Reference (formerly Polygon.io)

> **Scope.** This document describes the subset of the Massive REST API that FinAlly
> uses to retrieve **real-time / delayed prices for multiple tickers** and to
> **validate ticker symbols**. It is the source-of-truth for the `MassiveProvider`
> implementation described in [`MARKET_INTERFACE.md`](./MARKET_INTERFACE.md).
>
> "Massive" is this project's market-data provider. Polygon.io rebranded to
> **Massive** on **2025-10-30**; existing API keys, accounts, and integrations
> continue to work unchanged. In FinAlly, the environment variable is
> `MASSIVE_API_KEY` (see `PLAN.md` §5).

---

## 1. Base URL & Versioning

| Item | Value |
|---|---|
| Primary base URL | `https://api.massive.com` |
| Legacy base URL (still supported) | `https://api.polygon.io` |
| Protocol | HTTPS only |
| Response format | JSON |

Both hosts serve identical paths and responses. FinAlly uses
`https://api.massive.com`. Path versions are baked into each endpoint
(`/v2/...`, `/v3/...`) — there is no global version header.

---

## 2. Authentication

The API accepts the key **two** ways. Either is valid; prefer the header so the
key never lands in logs, proxies, or browser history.

### 2a. Authorization header (preferred)

```bash
curl "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT" \
  -H "Authorization: Bearer ${MASSIVE_API_KEY}"
```

### 2b. `apiKey` query parameter

```bash
curl "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT&apiKey=${MASSIVE_API_KEY}"
```

> FinAlly always uses the **Bearer header** form from server-side `httpx`.

### Error responses

| HTTP status | Meaning | Handling in FinAlly |
|---|---|---|
| `401 Unauthorized` | Missing/invalid key | Log once, fall back is **not** automatic — key was explicitly set, so surface a clear error |
| `403 Forbidden` | Key lacks plan entitlement for that endpoint/data | Log; the poller continues with whatever data it can read |
| `429 Too Many Requests` | Rate limit exceeded | Back off; see §6 |
| `200 OK` with `"status":"ERROR"` | App-level error in body | Inspect `error`/`message` fields in the JSON |

A `200` response can still carry a `status` of `OK`, `DELAYED`, or `ERROR` in the
body. Treat `OK` and `DELAYED` as success.

---

## 3. Rate Limits

| Plan | REST limit | Suitable poll interval (FinAlly) |
|---|---|---|
| **Free / Basic** | **5 requests / minute** | one request every **15 s** (4 req/min, safe margin) |
| Starter | 100 req/min | 2–5 s |
| Developer / Advanced / Business | Unlimited (fair use) | 1–2 s |

FinAlly polls **one batched request per cycle** (the multi-ticker snapshot, §4.1),
so a single request refreshes the entire tracked universe. This keeps the free
tier viable: at one snapshot every 15 s the app stays at ~4 req/min regardless of
how many tickers are watched.

Data freshness is also plan-dependent: Basic/Starter snapshots are **15-minute
delayed**; Advanced/Business are **real-time**. FinAlly treats whatever price the
snapshot returns as "current" — the UI does not distinguish delayed vs real-time.

---

## 4. Endpoints Used by FinAlly

### 4.1 Full Market Snapshot — multi-ticker prices (PRIMARY)

The workhorse. One request returns the latest day bar, previous-day bar, last
trade, last quote, and minute bar for **a comma-separated list of tickers** (or
the whole market if omitted). This is what the background poller calls every
cycle.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

**Query parameters**

| Param | Type | Required | Notes |
|---|---|---|---|
| `tickers` | string | No | Case-sensitive, comma-separated (e.g. `AAPL,MSFT,TSLA`). **Omit to get all ~10,000 tickers.** FinAlly always passes the explicit tracked set. |
| `include_otc` | boolean | No | Default `false`. FinAlly leaves it `false`. |

**Example request**

```bash
curl "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT" \
  -H "Authorization: Bearer ${MASSIVE_API_KEY}"
```

**Example response**

```json
{
  "status": "OK",
  "count": 2,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.23,
      "todaysChangePerc": 0.65,
      "updated": 1699564800000000000,
      "day":     { "o": 189.9, "h": 191.5, "l": 189.1, "c": 190.4, "v": 41250000, "vw": 190.3 },
      "min":     { "av": 41250000, "t": 1699564740000, "o": 190.3, "h": 190.5, "l": 190.2, "c": 190.4, "v": 12000, "vw": 190.38, "n": 95 },
      "prevDay": { "o": 188.4, "h": 189.7, "l": 187.9, "c": 189.17, "v": 50230000, "vw": 188.9 },
      "lastTrade": { "p": 190.42, "s": 100, "t": 1699564799000000000, "x": 11, "c": [12], "i": "12345" },
      "lastQuote": { "P": 190.45, "S": 2, "p": 190.40, "s": 3, "t": 1699564799000000000 }
    },
    {
      "ticker": "MSFT",
      "todaysChange": -2.10,
      "todaysChangePerc": -0.55,
      "updated": 1699564800000000000,
      "day":     { "o": 379.0, "h": 381.2, "l": 376.5, "c": 377.8, "v": 18900000, "vw": 378.6 },
      "min":     { "av": 18900000, "t": 1699564740000, "o": 377.9, "h": 378.1, "l": 377.6, "c": 377.8, "v": 8000, "vw": 377.85, "n": 70 },
      "prevDay": { "o": 381.5, "h": 382.9, "l": 379.0, "c": 379.9, "v": 22100000, "vw": 380.7 },
      "lastTrade": { "p": 377.80, "s": 50, "t": 1699564799000000000, "x": 12, "c": [14], "i": "67890" },
      "lastQuote": { "P": 377.85, "S": 1, "p": 377.78, "s": 2, "t": 1699564799000000000 }
    }
  ]
}
```

**Top-level fields**

| Field | Type | Description |
|---|---|---|
| `status` | string | `OK`, `DELAYED`, or `ERROR` |
| `count` | int | Number of ticker objects returned |
| `tickers` | array | One snapshot object per requested ticker (see below) |

**Per-ticker snapshot object**

| Field | Type | Description |
|---|---|---|
| `ticker` | string | Symbol |
| `todaysChange` | number | Absolute change vs previous close |
| `todaysChangePerc` | number | Percentage change vs previous close |
| `updated` | int | Last update time (**Unix nanoseconds**) |
| `day` | object | Today's aggregate bar so far |
| `min` | object | Most recent minute bar |
| `prevDay` | object | Previous trading day's bar |
| `lastTrade` | object | Most recent trade |
| `lastQuote` | object | Most recent NBBO quote |
| `fmv` | number | Fair market value (Business plan only) |

**Bar object** (`day`, `min`, `prevDay`)

| Key | Meaning |
|---|---|
| `o` `h` `l` `c` | open / high / low / close |
| `v` | volume |
| `vw` | volume-weighted average price |
| `av` | accumulated day volume (`min` only) |
| `n` | number of transactions (`min` only) |
| `t` | bar start timestamp, **Unix ms** (`min` only) |

**`lastTrade`**: `p` price · `s` size · `t` timestamp (ns) · `x` exchange id · `c` trade conditions · `i` trade id.

**`lastQuote`**: `P` ask price · `S` ask size · `p` bid price · `s` bid size · `t` timestamp (ns).

#### Which field is "the price"?

FinAlly derives the current price with this fallback chain (first non-null wins):

1. `lastTrade.p` — true last-traded price (real-time plans)
2. `min.c` — latest minute close (good on delayed plans / illiquid names)
3. `day.c` — today's close-so-far
4. `prevDay.c` — fallback before the market opens

> **Caveat — missing tickers.** If a requested ticker is invalid, halted, or has
> no data yet, it may be **absent** from the `tickers` array (the response is not
> padded). Callers must tolerate `count < len(requested)` and key results by
> `ticker`. Outside market hours, `lastTrade`/`min` can be stale and the response
> is largely `prevDay` data — this is expected, not an error.

---

### 4.2 Single Ticker Snapshot

Same shape as one element of §4.1, useful for a one-off lookup.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}
```

**Example**

```bash
curl "https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers/AAPL" \
  -H "Authorization: Bearer ${MASSIVE_API_KEY}"
```

```json
{
  "status": "OK",
  "request_id": "657e4...",
  "ticker": {
    "ticker": "AAPL",
    "todaysChange": 1.23,
    "todaysChangePerc": 0.65,
    "updated": 1699564800000000000,
    "day":     { "o": 189.9, "h": 191.5, "l": 189.1, "c": 190.4, "v": 41250000, "vw": 190.3 },
    "min":     { "o": 190.3, "h": 190.5, "l": 190.2, "c": 190.4, "v": 12000, "vw": 190.38, "n": 95, "t": 1699564740000 },
    "prevDay": { "o": 188.4, "h": 189.7, "l": 187.9, "c": 189.17, "v": 50230000, "vw": 188.9 },
    "lastTrade": { "p": 190.42, "s": 100, "t": 1699564799000000000, "x": 11 },
    "lastQuote": { "P": 190.45, "S": 2, "p": 190.40, "s": 3, "t": 1699564799000000000 }
  }
}
```

Note the wrapper differs from §4.1: top-level `ticker` is a **single object**, not
an array.

---

### 4.3 Tickers Reference — symbol validation (`is_supported`)

Used to validate watchlist additions when Massive is the active provider
(`is_supported`, PLAN.md §6). The simulator validates against its seed set; Massive
validates against the provider's universe via this endpoint.

```
GET /v3/reference/tickers
```

**Query parameters**

| Param | Type | Notes |
|---|---|---|
| `ticker` | string | Exact symbol match. **This is how FinAlly validates** — request the exact ticker. |
| `search` | string | Fuzzy search over symbol + company name (for autocomplete, not validation) |
| `active` | boolean | Default `true`. Only currently-traded symbols. |
| `market` | string | `stocks`, `crypto`, `fx`, `otc`, `indices`. FinAlly uses `stocks`. |
| `limit` | int | Default 100, max 1000 |

**Validation example**

```bash
curl "https://api.massive.com/v3/reference/tickers?ticker=AAPL&active=true&market=stocks&limit=1" \
  -H "Authorization: Bearer ${MASSIVE_API_KEY}"
```

```json
{
  "status": "OK",
  "count": 1,
  "request_id": "1f2c...",
  "results": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "market": "stocks",
      "locale": "us",
      "primary_exchange": "XNAS",
      "type": "CS",
      "active": true,
      "currency_name": "usd",
      "cik": "0000320193",
      "composite_figi": "BBG000B9XRY4",
      "last_updated_utc": "2025-10-30T00:00:00Z"
    }
  ],
  "next_url": null
}
```

**`is_supported(ticker)` rule:** request `?ticker=<SYMBOL>&active=true&market=stocks&limit=1`;
the symbol is supported iff `count >= 1` **and** the first result's `ticker`
equals the requested symbol (case-insensitive compare, but send upper-case).

**Result fields of interest:** `ticker`, `name`, `market`, `active`,
`primary_exchange`, `type` (`CS` common stock, `ETF`, etc.), `currency_name`.

> Cache validation results. The universe changes rarely, so FinAlly memoises
> `is_supported` answers for the process lifetime to avoid burning the rate limit
> on repeated adds of the same symbol.

---

### 4.4 Previous Day Bar (optional / fallback)

Single-ticker previous trading day OHLC. Cheap pre-market fallback for a sane
reference price.

```
GET /v2/aggs/ticker/{stocksTicker}/prev
```

| Query param | Notes |
|---|---|
| `adjusted` | boolean, default `true` (split-adjusted) |

```bash
curl "https://api.massive.com/v2/aggs/ticker/AAPL/prev?adjusted=true" \
  -H "Authorization: Bearer ${MASSIVE_API_KEY}"
```

```json
{
  "ticker": "AAPL",
  "adjusted": true,
  "queryCount": 1,
  "resultsCount": 1,
  "status": "OK",
  "request_id": "6a7e466...",
  "results": [
    { "T": "AAPL", "o": 188.4, "h": 189.7, "l": 187.9, "c": 189.17, "v": 50230000, "vw": 188.9, "t": 1605042000000 }
  ]
}
```

`results[].c` is the previous close. Note bar keys here are `o/h/l/c/v/vw/t` plus
`T` (symbol) — same shorthand as the snapshot bars.

---

### 4.5 Custom Bars / Aggregates (NOT used)

```
GET /v2/aggs/ticker/{stocksTicker}/range/{multiplier}/{timespan}/{from}/{to}
```

FinAlly intentionally does **not** use historical aggregates: per PLAN.md §10 /
Decision #2, charts accumulate from the SSE stream since page load, and there is
no historical-price endpoint in the app. Documented here only so future work
doesn't re-derive it. Path params: `multiplier` (int), `timespan`
(`minute|hour|day|...`), `from`/`to` (YYYY-MM-DD or epoch ms). Query: `adjusted`,
`sort` (`asc|desc`), `limit` (max 50000). Returns `results[]` of
`{o,h,l,c,v,vw,t,n}` with `next_url` pagination.

### 4.6 Grouped Daily / Daily Market Summary (NOT used)

```
GET /v2/aggs/grouped/locale/us/market/stocks/{date}
```

Whole-market OHLC for one date in a single call. Not needed by FinAlly (the
multi-ticker snapshot covers our live use case). Listed for completeness.

---

## 5. Endpoint Selection Summary

| FinAlly need | Endpoint | Frequency |
|---|---|---|
| Live prices for all tracked tickers | `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=...` (§4.1) | Every poll cycle (15 s free tier) |
| Validate a watchlist add (`is_supported`) | `GET /v3/reference/tickers?ticker=...` (§4.3) | On demand, memoised |
| Pre-market reference price fallback | `GET /v2/aggs/ticker/{t}/prev` (§4.4) | Optional, rare |

---

## 6. Operational Notes for the Poller

- **Batch, don't loop.** Always send the full tracked set in one `tickers=` query.
  Never issue one request per symbol — that multiplies rate-limit cost by N.
- **Poll interval is config-driven.** Default 15 s (free-tier safe). Drive it from
  an env var / setting so paid keys can poll faster. See `MARKET_INTERFACE.md`.
- **Timestamps are mixed units.** `updated`, `lastTrade.t`, `lastQuote.t` are
  **nanoseconds**; bar `t` (`min.t`, `prevDay`-via-`/prev`) is **milliseconds**.
  Normalise to seconds/ms internally when building the cache.
- **429 backoff.** On `429`, skip writes for that cycle and lengthen the next
  interval (e.g. exponential backoff capped at 60 s), then recover. Never crash
  the background task.
- **Tolerate gaps.** Missing tickers, null `lastTrade`, and `DELAYED` status are
  normal — fall through the price chain in §4.1 and keep the last known cache value
  if a cycle yields nothing for a symbol.
- **Network timeouts.** Use a finite `httpx` timeout (e.g. 10 s). A hung request
  must not stall the whole poll loop.

---

## 7. Official Python Client (reference)

The official client is published on PyPI as **`massive`** (the renamed
`polygon-api-client`).

```bash
pip install -U massive    # or: uv add massive
```

```python
from massive import RESTClient

client = RESTClient(api_key=os.environ["MASSIVE_API_KEY"])

# Multi-ticker snapshot (market_type, tickers list)
snapshots = client.get_snapshot_all("stocks", tickers=["AAPL", "MSFT"])
for s in snapshots:
    print(s.ticker, s.last_trade.price, s.prev_day.close)

# Single ticker snapshot
one = client.get_snapshot_ticker("stocks", "AAPL")

# Reference / validation (auto-paginating iterator)
for t in client.list_tickers(ticker="AAPL", market="stocks", active=True, limit=1):
    print(t.ticker, t.name)

# Previous close
prev = client.get_previous_close_agg("AAPL")
```

> **FinAlly uses raw `httpx` against the REST endpoints above**, not this client,
> because the backend is fully async (FastAPI) and we want explicit control over
> the single batched poll, timeouts, and `429` backoff. The client is documented
> here as a cross-check on field names and as an option for synchronous scripts.

---

## 8. Sources

- [Full Market Snapshot — Massive docs](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)
- [Single Ticker Snapshot — Massive docs](https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot)
- [Tickers Reference (All Tickers) — Massive docs](https://massive.com/docs/rest/stocks/tickers/all-tickers)
- [Previous Day Bar — Massive docs](https://massive.com/docs/rest/stocks/aggregates/previous-day-bar)
- [Custom Bars — Massive docs](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
- [Daily Market Summary (grouped) — Massive docs](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary)
- [REST API Quickstart — Massive docs](https://massive.com/docs/rest/quickstart)
- [Official Python client — github.com/massive-com/client-python](https://github.com/massive-com/client-python)
- [Polygon.io is now Massive — announcement](https://massive.com/blog/polygon-is-now-massive)
