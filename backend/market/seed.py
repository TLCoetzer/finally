from dataclasses import dataclass


@dataclass(frozen=True)
class TickerSpec:
    seed_price: float
    annual_drift: float  # mu  — expected annual return (0.08 = +8%/yr)
    annual_vol: float    # sigma — annualized volatility (0.30 = 30%)
    sector: str          # correlation grouping


# Seed prices double as "session open" values AND the supported universe.
# Must include the 10 default watchlist tickers (PLAN.md §7) plus margin to add.
UNIVERSE: dict[str, TickerSpec] = {
    # --- default watchlist tickers ---
    "AAPL":  TickerSpec(190.0, 0.10, 0.28, "tech"),
    "GOOGL": TickerSpec(175.0, 0.09, 0.30, "tech"),
    "MSFT":  TickerSpec(420.0, 0.11, 0.26, "tech"),
    "AMZN":  TickerSpec(185.0, 0.10, 0.33, "tech"),
    "TSLA":  TickerSpec(250.0, 0.05, 0.55, "auto"),
    "NVDA":  TickerSpec(120.0, 0.18, 0.50, "tech"),
    "META":  TickerSpec(500.0, 0.12, 0.35, "tech"),
    "JPM":   TickerSpec(200.0, 0.06, 0.22, "finance"),
    "V":     TickerSpec(280.0, 0.08, 0.20, "finance"),
    "NFLX":  TickerSpec(630.0, 0.10, 0.38, "media"),
    # --- extras so users have symbols to add ---
    "AMD":   TickerSpec(160.0, 0.14, 0.48, "tech"),
    "INTC":  TickerSpec(35.0,  0.02, 0.34, "tech"),
    "DIS":   TickerSpec(100.0, 0.05, 0.30, "media"),
    "BAC":   TickerSpec(38.0,  0.05, 0.26, "finance"),
    "WMT":   TickerSpec(70.0,  0.07, 0.18, "retail"),
    "KO":    TickerSpec(62.0,  0.04, 0.15, "consumer"),
    "PYPL":  TickerSpec(65.0,  0.04, 0.40, "finance"),
    "F":     TickerSpec(12.0,  0.03, 0.35, "auto"),
}

SEED_PRICES: dict[str, float] = {t: s.seed_price for t, s in UNIVERSE.items()}

DEFAULT_WATCHLIST: list[str] = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]
