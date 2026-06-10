"use client";

// Trade bar (PLAN.md §10): ticker + quantity, Buy/Sell. Market orders, instant
// fill, no confirmation dialog. Result/error is surfaced inline.
import { useEffect, useState } from "react";
import type { TradeResponse, TradeSide } from "@/lib/types";

interface Props {
  selectedTicker?: string | null;
  onTrade: (ticker: string, quantity: number, side: TradeSide) => Promise<TradeResponse>;
}

export function TradeBar({ selectedTicker, onTrade }: Props) {
  const [ticker, setTicker] = useState(selectedTicker ?? "");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // Prefill the ticker field when the user selects one in the watchlist.
  useEffect(() => {
    if (selectedTicker) setTicker(selectedTicker);
  }, [selectedTicker]);

  async function submit(side: TradeSide) {
    const t = ticker.trim().toUpperCase();
    const q = Number(qty);
    if (!t || !Number.isFinite(q) || q <= 0) {
      setMsg({ kind: "err", text: "Enter a ticker and a positive quantity." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await onTrade(t, q, side);
      setMsg({
        kind: "ok",
        text: `${res.side.toUpperCase()} ${res.quantity} ${res.ticker} @ $${res.price.toFixed(2)}`,
      });
      setQty("");
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Trade failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" data-testid="trade-bar">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
        <span className="panel-title mr-1">Trade</span>
        <input
          data-testid="trade-ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="TICKER"
          aria-label="Trade ticker"
          className="field w-28 uppercase"
        />
        <input
          data-testid="trade-qty"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          placeholder="Qty"
          inputMode="decimal"
          aria-label="Trade quantity"
          className="field w-24"
        />
        <button
          type="button"
          data-testid="trade-buy"
          disabled={busy}
          onClick={() => submit("buy")}
          className="btn btn-buy"
        >
          Buy
        </button>
        <button
          type="button"
          data-testid="trade-sell"
          disabled={busy}
          onClick={() => submit("sell")}
          className="btn btn-sell"
        >
          Sell
        </button>
        {msg && (
          <span
            data-testid="trade-message"
            className={`text-xs ${msg.kind === "ok" ? "text-up" : "text-down"}`}
          >
            {msg.text}
          </span>
        )}
      </div>
    </section>
  );
}
