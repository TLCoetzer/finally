# Market Data Backend — Code Review

> **Date:** 2026-06-07
> **Scope reviewed:** the market-data subsystem under `backend/` — `market/`
> (`types`, `cache`, `provider`, `seed`, `simulator`, `massive`, `factory`,
> `sse`), `api/stream.py`, `api/deps.py`, `tracking.py`, `app.py`, `db.py`, and
> the test suite in `backend/tests/`.
> **Reference specs:** `PLAN.md` §6/§8/§10, `MARKET_DATA_DESIGN.md`,
> `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, `MASSIVE_API.md`.

## 1. Verdict

The implementation is a faithful, clean realisation of the design documents. The
module layout, the single-writer cache, the provider abstraction, the GBM
simulator, the Massive REST client, and the SSE endpoint all match their specs.
Test coverage is good for the units that exist.

There is **one failing (flaky) test**, **two latent correctness bugs** that will
surface once the real `db.py` is wired in, and a handful of quality/robustness
items. None block the current "market data layer" milestone, but B1 and L1/L2
should be fixed before the database layer lands.

## 2. How tests were run

The system `python` on PATH is Anaconda **3.8/3.9**; `pyproject.toml` pins
`requires-python >=3.12`. `cache.py`, `factory.py`, `deps.py`, `sse.py`, and
`stream.py` use PEP 604 `X | None` annotations **without**
`from __future__ import annotations`, so they evaluate at runtime and fail to
import on <3.10. Running the suite against Anaconda therefore errors at
collection. The correct invocation lets uv provision 3.12:

```
cd backend
uv run --python 3.12 --extra dev pytest -q
```

(`pytest`/`pytest-asyncio`/`respx` are optional `dev` extras, so `--extra dev`
is required.)

### Result

`94 tests`. Outcome **varies run to run with no code change**:

```
94 passed in 1.36s          # one run
1 failed, 93 passed         # an earlier identical run
```

Isolating the offender across six fresh processes: 3 passed / 3 failed. The
single non-deterministic test is
`tests/test_simulator.py::test_same_sector_correlates_more_than_cross_sector`.
Everything else passes deterministically.

## 3. Findings

### B1 — Flaky correlation test (blocking the green build) — confirmed

`test_same_sector_correlates_more_than_cross_sector` passes or fails depending on
`PYTHONHASHSEED`:

```
PYTHONHASHSEED=1 -> passed
PYTHONHASHSEED=2 -> passed
PYTHONHASHSEED=3 -> failed   Expected tech-tech (0.067) > tech-finance (0.212)
```

Two compounding root causes, both proven:

1. **RNG draw order is not actually seeded.** In `simulator._step`:

   ```python
   sectors = {s.spec.sector for s in self._state.values()}   # a set
   z_sector = {sec: self._rng.gauss(0.0, 1.0) for sec in sectors}
   ```

   Iteration order over a `set` of sector **strings** depends on
   `PYTHONHASHSEED`, so the order in which the per-sector Gaussians are drawn
   from `self._rng` changes between processes. The "deterministic when seeded"
   guarantee (`MARKET_SIMULATOR.md` §1, §8) therefore holds only *within one
   process*. `test_reproducible_with_seeded_rng` passes only because both sims
   run in the same process (same hash seed); it would not reproduce across runs.

2. **Cent-rounding quantises the signal away.** Prices are written to the cache
   rounded to cents, and the test computes log-returns from those cached values.
   At a 0.5 s tick the true per-tick move is sub-cent:

   ```
   AAPL per-tick move ~ 190 * 0.28 * sqrt(0.5 / 31_536_000) = $0.0067  (< $0.01)
   ```

   Most ticks round to a 0- or 1-cent change, so the measured correlation is
   dominated by quantisation noise (~0.07 for both same- and cross-sector). With
   the signal that weak, the `corr_tech > corr_cross` assertion is a coin flip.

   The simulator itself is correct here (internal price stays full precision; the
   cent rounding on the wire is by design, `MARKET_SIMULATOR.md` §6). The **test**
   is measuring the wrong series.

**Fix.** Make the draw order deterministic (`for sec in sorted(sectors)`), which
removes the hash dependence. Then make the statistical test robust to
quantisation — e.g. assert correlation on full-precision internal prices, or
raise the tick/horizon so cumulative moves clear the cent grid and the
quantisation averages out, with a looser margin.

### L1 — Empty tracked set resurrects the whole universe (simulator) — confirmed

`simulator._step` uses `targets = self._tracked or set(self._state)`. The
`or` cannot distinguish "tracked never set yet" from "tracked is legitimately
empty". Proven:

```
after set_tracked({'AAPL'})  -> cache size 1
after set_tracked(set())     -> cache size 18   # all of UNIVERSE re-created
```

`set_tracked(set())` first drops every cached ticker, then `_step` falls back to
the full universe and re-populates all 18. `MassiveProvider._poll_once` does the
opposite (`if not tickers: return` → cache stays empty). So once `db.py` is real
and a user clears the watchlist with no open positions, the simulator silently
streams all 18 symbols while Massive streams none — a provider divergence and a
leak of unwatched tickers into the SSE stream.

**Fix.** Track "initialised" explicitly (a `bool`, or `self._tracked: set | None
= None` sentinel) so the whole-universe fallback applies only before the first
`set_tracked`, never to a deliberately empty set. Make both providers agree.

### L2 — Massive `is_supported` permanently caches transient failures — confirmed by read

```python
except Exception:
    ok = False          # fail closed
self._supported[t] = ok # cached for the process lifetime
```

Failing closed on the *immediate* decision is correct, but the result is then
memoised forever. A single network blip / timeout / 5xx while validating a
**valid** symbol caches `False`, so the user (or the AI) can never add that
ticker again until the process restarts. `MASSIVE_API.md` §4.3 asks to memoise to
save rate limit, but only definitive answers should be cached.

**Fix.** Cache only definitive outcomes — `True`, and a confirmed "not found"
(`200` with empty/ mismatched `results`). On network/HTTP exceptions, return
`False` for this call but do **not** store it, so a later retry can succeed.

### M1 — No logging; loops swallow everything silently

`simulator._loop`, `massive._loop`, and `massive._poll_once` catch broad
`Exception` and `pass`. The market layer has no logging at all. A bad
`MASSIVE_API_KEY` makes the Massive loop retry every 15 s forever with no signal;
`MASSIVE_API.md` §2 specifically asks to "log once" on `401`. Add minimal
logging (at least once-per-condition for 401/403 and unexpected exceptions) so
production failures are diagnosable. Keep the "never kill the loop" behaviour.

### M2 — Inconsistent `from __future__ import annotations`

`types.py`, `provider.py`, `simulator.py`, `massive.py` have it; `cache.py`,
`factory.py`, `deps.py`, `sse.py`, `stream.py` do not. Harmless on the pinned
3.12, but it is the reason the suite cannot even be collected on the Anaconda
interpreter that is first on PATH. Add the import to the five modules for
consistency and import-safety, or rely on it nowhere and standardise.

### M3 — `_extract_price` truthiness edge

The fallback chain uses `if v:` to accept a field. A numeric `0` is correctly
skipped (tested), but a **string** `"0"`/`"0.00"` from the API would be truthy
and return `0.0`. Unlikely from Massive, but an explicit `v not in (None, 0)`
(or `float(v) != 0`) would be safer than truthiness.

### M4 — Factory: no tests, and brittle env parsing

`create_provider` (the env-var selection of simulator vs Massive, and
`MASSIVE_POLL_SECONDS`) has **no test**, despite being the switch the whole
provider design hinges on. Also `float(os.environ.get("MASSIVE_POLL_SECONDS",
"15"))` raises `ValueError` at startup on a malformed value. Add tests
(key set → Massive, unset/blank → simulator) and consider tolerating a bad poll
value.

### M5 — Scope: only the stream endpoint is wired

`app.py` includes only `stream.router`. The watchlist / portfolio / health routes
from `MARKET_DATA_DESIGN.md` §10 are not implemented, and `db.py` is an
acknowledged stub returning empty lists. That is consistent with a "market data
layer first" milestone, but note the consequences: `recompute_tracked` /
`tracking.py` and `deps.get_provider` are currently exercised by nothing (no
tests, and `get_provider` is unused until a route needs it), and the
`is_supported` + `recompute_tracked` watchlist-add gate (Decision #5) is not yet
end-to-end. L1 above is dormant precisely because the stub keeps tracked empty →
universe fallback; it activates the moment `db.py` returns real tickers.

### M6 — The "integration" SSE test does not exercise the real endpoint

`tests/test_stream.py` builds a **separate** minimal FastAPI app with its own
one-shot generator rather than mounting `api.stream.router`. So the real
`stream_prices` / `_price_event_gen` path — `Depends(get_cache)`, the heartbeat,
the `request.is_disconnected()` loop, and the response headers
(`X-Accel-Buffering` etc.) — is never integration-tested through the router.
`_price_event_gen` is unit-tested directly in `test_sse.py`, which is good, but
an end-to-end test against the actual router (using `ASGITransport` and a cache
on `app.state`) would close the gap.

### M7 — No cross-provider conformance suite

`MARKET_INTERFACE.md` §9 and `MARKET_DATA_DESIGN.md` §13.2 call for a single
parametrised suite asserting both providers satisfy the `MarketDataProvider`
contract and emit the same `Quote` shape. The current tests cover each provider
separately but never assert the shared contract in one place.

### M8 — No committed lockfile

Only `pyproject.toml` is tracked; there is no `uv.lock`. For the reproducible-
environment goal (and CI), commit the lock.

## 4. What is done well

- Architecture matches the design exactly: self-contained `market/` package with
  no FastAPI dependency; FastAPI only in `api/` and `app.py`.
- `Quote` is a frozen dataclass; the reference-price "first price wins, never
  mutated" invariant lives solely in `cache.update` and is well tested
  (`test_reference_price_never_changes`, `test_reference_price_fixed_across_many_ticks`).
- `PriceCache` is the single source of truth: lock-guarded, copy-on-read `all()`,
  case-normalised keys; thread-safety smoke test included.
- GBM correctness is genuinely tested: zero-volatility deterministic growth
  against the closed form, strict positivity, finiteness, and seeded
  reproducibility within a process.
- The Massive client covers the documented behaviours: batched single request,
  price fallback chain (with null/zero tolerance), ns→s timestamp conversion,
  `429` exponential backoff with recovery, memoised `is_supported`, fail-closed
  validation, and the API key kept out of URLs/logs.
- SSE serialisation emits exactly the `PLAN.md` §6 field set plus `change_pct`,
  with heartbeat and disconnect handling.

## 5. Recommended priority

1. **B1** — fix the flaky test (sort the sector draw order; assert correlation on
   full-precision prices). Required for a trustworthy green build.
2. **L1, L2** — fix before `db.py` lands; both are dormant only because of the
   stub.
3. **M1, M2, M4** — small, high-value robustness/consistency fixes.
4. **M5–M8** — close as the watchlist/portfolio/health routes and real DB are
   implemented.
