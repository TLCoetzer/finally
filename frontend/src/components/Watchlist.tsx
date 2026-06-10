"use client";

// Watchlist panel: live grid of tickers + an add field. Add/remove call the
// backend and surface validation errors (unsupported tickers → 400, PLAN.md §8).
import { useState } from "react";
import { WatchlistRow } from "./WatchlistRow";
import type { PriceFrame, PricePoint } from "@/lib/types";

interface Props {
  tickers: string[];
  quotes: Record<string, PriceFrame>;
  history: Record<string, PricePoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => void;
}

export function Watchlist({
  tickers,
  quotes,
  history,
  selected,
  onSelect,
  onAdd,
  onRemove,
}: Props) {
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = input.trim().toUpperCase();
    if (!t) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(t);
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add ticker");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel flex h-full flex-col" data-testid="watchlist-panel">
      <div className="panel-head">
        <h2 className="panel-title">Watchlist</h2>
        <span className="text-[10px] text-muted">{tickers.length} symbols</span>
      </div>

      <form onSubmit={submit} className="flex items-center gap-2 px-3 py-2">
        <input
          data-testid="watchlist-add-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add ticker (e.g. PYPL)"
          className="field w-full uppercase"
          aria-label="Add ticker"
        />
        <button
          type="submit"
          data-testid="watchlist-add-button"
          disabled={busy || !input.trim()}
          className="btn btn-submit whitespace-nowrap"
        >
          Add
        </button>
      </form>
      {error && (
        <p data-testid="watchlist-error" className="px-3 pb-2 text-xs text-down">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-ink-800/95 backdrop-blur">
            <tr className="text-[9px] uppercase tracking-[0.16em] text-muted/70">
              <th className="px-3 py-1.5 text-left font-medium">Sym</th>
              <th className="px-3 py-1.5 text-right font-medium">Last</th>
              <th className="px-3 py-1.5 text-right font-medium">Chg%</th>
              <th className="px-3 py-1.5 text-right font-medium">Trend</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tickers.map((ticker) => (
              <WatchlistRow
                key={ticker}
                ticker={ticker}
                frame={quotes[ticker]}
                history={history[ticker] ?? []}
                selected={selected === ticker}
                onSelect={onSelect}
                onRemove={onRemove}
              />
            ))}
            {tickers.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-xs text-muted">
                  No tickers. Add one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
