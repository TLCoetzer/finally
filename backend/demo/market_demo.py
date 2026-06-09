"""Rich terminal demo for the market-data simulator.

Streams the in-process GBM SimulatorProvider into a live-updating terminal
dashboard: per-ticker last price (flashing green/red on an uptick/downtick),
absolute and percent change versus the session reference price, a direction
arrow, and a unicode sparkline accumulated from the stream since launch.

Run from the backend/ directory:

    uv run --python 3.12 --extra demo python -m demo.market_demo
    uv run --python 3.12 --extra demo python -m demo.market_demo --seed 42 --tickers AAPL,NVDA,TSLA
    uv run --python 3.12 --extra demo python -m demo.market_demo --duration 10   # auto-exit (good for CI/smoke)

The rich import is deferred into the rendering functions so the pure helpers
below stay importable (and unit-testable) without the demo extra installed.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from collections import deque
from typing import Iterable

from market.cache import PriceCache
from market.seed import DEFAULT_WATCHLIST, UNIVERSE
from market.simulator import SimulatorProvider
from market.types import Direction, Quote

# Project palette (PLAN.md): accent yellow, primary blue, secondary purple.
ACCENT = "#ecad0a"
BLUE = "#209dd7"

SPARK_CHARS = "▁▂▃▄▅▆▇█"
UP, DOWN, FLAT = "▲", "▼", "—"


# ---- pure helpers (no rich dependency) -----------------------------------

def sparkline(values: Iterable[float]) -> str:
    """Render a sequence of values as a unicode block sparkline.

    Scales between the run's min and max. A flat or single-value series
    renders as the lowest block."""
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span <= 0:
        return SPARK_CHARS[0] * len(vals)
    last = len(SPARK_CHARS) - 1
    return "".join(SPARK_CHARS[int((v - lo) / span * last)] for v in vals)


def resolve_tickers(raw: str | None) -> list[str]:
    """Parse a comma-separated --tickers value, keeping only known symbols.

    Falls back to the default watchlist when nothing valid is supplied."""
    if not raw:
        return list(DEFAULT_WATCHLIST)
    requested = [t.strip().upper() for t in raw.split(",") if t.strip()]
    valid = [t for t in requested if t in UNIVERSE]
    return valid or list(DEFAULT_WATCHLIST)


def direction_glyph(direction: Direction) -> tuple[str, str]:
    """Return (arrow, rich-style) for a price direction."""
    if direction is Direction.UP:
        return UP, "bold green"
    if direction is Direction.DOWN:
        return DOWN, "bold red"
    return FLAT, "dim"


# ---- rendering (rich) ----------------------------------------------------

def build_table(tickers, snapshot: dict[str, Quote], history):
    """Build the live price table from the current cache snapshot."""
    from rich import box
    from rich.table import Table

    table = Table(box=box.SIMPLE_HEAVY, expand=True, pad_edge=False)
    table.add_column("Ticker", style="bold", no_wrap=True)
    table.add_column("Last", justify="right", no_wrap=True)
    table.add_column("Chg", justify="right", no_wrap=True)
    table.add_column("Chg %", justify="right", no_wrap=True)
    table.add_column("Dir", justify="center", no_wrap=True)
    table.add_column("Trend", justify="left", no_wrap=True)

    for ticker in tickers:
        q = snapshot.get(ticker)
        if q is None:
            table.add_row(ticker, "-", "-", "-", "-", "")
            continue
        arrow, arrow_style = direction_glyph(q.direction)
        chg = q.change
        chg_style = "green" if chg > 0 else "red" if chg < 0 else "dim"
        spark_style = "green" if chg > 0 else "red" if chg < 0 else "grey50"
        table.add_row(
            ticker,
            f"{q.price:,.2f}",
            f"[{chg_style}]{chg:+,.2f}[/]",
            f"[{chg_style}]{q.change_pct:+.2f}%[/]",
            f"[{arrow_style}]{arrow}[/]",
            f"[{spark_style}]{sparkline(history[ticker])}[/]",
        )
    return table


def build_view(tickers, snapshot, history, elapsed: float, source: str, tick: float):
    """Compose the header panel and the price table into one renderable."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    title = Text("FinAlly", style=f"bold {ACCENT}")
    title.append("  Market Data Simulator", style=f"bold {BLUE}")

    subtitle = (
        f"source: {source}   tickers: {len(tickers)}   "
        f"tick: {tick:.2f}s   elapsed: {elapsed:5.1f}s"
    )
    header = Panel(title, subtitle=subtitle, border_style=BLUE)
    footer = Text("Press Ctrl+C to quit", style="dim italic")
    return Group(header, build_table(tickers, snapshot, history), footer)


# ---- run loop ------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    cache = PriceCache()
    rng = random.Random(args.seed) if args.seed is not None else None
    sim = SimulatorProvider(cache, tick_seconds=args.tick, rng=rng)

    tickers = resolve_tickers(args.tickers)
    sim.set_tracked(set(tickers))
    history: dict[str, deque] = {t: deque(maxlen=args.spark_width) for t in tickers}

    from rich.console import Console
    from rich.live import Live

    console = Console()
    start = time.monotonic()
    await sim.start()
    try:
        with Live(console=console, screen=False, refresh_per_second=max(1, int(1 / args.refresh))) as live:
            while True:
                elapsed = time.monotonic() - start
                snapshot = cache.all()
                for t in tickers:
                    q = snapshot.get(t)
                    if q is not None:
                        history[t].append(q.price)
                live.update(build_view(tickers, snapshot, history, elapsed, sim.source, args.tick))
                if args.duration is not None and elapsed >= args.duration:
                    break
                await asyncio.sleep(args.refresh)
    finally:
        await sim.stop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rich terminal demo for the market simulator.")
    parser.add_argument("--tickers", help="comma-separated symbols (default: the seed watchlist)")
    parser.add_argument("--seed", type=int, help="RNG seed for a reproducible run")
    parser.add_argument("--tick", type=float, default=0.5, help="simulator tick seconds (default 0.5)")
    parser.add_argument("--refresh", type=float, default=0.25, help="UI refresh interval seconds (default 0.25)")
    parser.add_argument("--spark-width", type=int, default=24, help="sparkline history length (default 24)")
    parser.add_argument("--duration", type=float, help="auto-exit after N seconds (default: run until Ctrl+C)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    # The unicode sparklines/arrows need a UTF-8 stream; on Windows a redirected
    # stdout defaults to cp1252 and would raise. Reconfigure best-effort.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = parse_args(argv)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
