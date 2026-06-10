"use client";

// Positions table (PLAN.md §10): ticker, qty, avg cost, current price,
// unrealized P&L, and % change vs avg_cost. Prices and P&L update live from
// the stream via livePositions().
import {
  changeClass,
  formatPct,
  formatPrice,
  formatQty,
  formatSignedUsd,
} from "@/lib/format";
import type { LivePosition } from "@/lib/portfolio";

interface Props {
  positions: LivePosition[];
  onSelect: (ticker: string) => void;
}

export function PositionsTable({ positions, onSelect }: Props) {
  return (
    <section className="panel flex h-full flex-col" data-testid="positions-panel">
      <div className="panel-head">
        <h2 className="panel-title">Positions</h2>
        <span className="text-[10px] text-muted">{positions.length} holdings</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-ink-800/95 backdrop-blur">
            <tr className="text-[9px] uppercase tracking-[0.16em] text-muted/70">
              <th className="px-3 py-1.5 text-left font-medium">Sym</th>
              <th className="px-3 py-1.5 text-right font-medium">Qty</th>
              <th className="px-3 py-1.5 text-right font-medium">Avg</th>
              <th className="px-3 py-1.5 text-right font-medium">Last</th>
              <th className="px-3 py-1.5 text-right font-medium">P&L</th>
              <th className="px-3 py-1.5 text-right font-medium">%</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr
                key={p.ticker}
                data-testid={`position-row-${p.ticker}`}
                onClick={() => onSelect(p.ticker)}
                className="cursor-pointer border-b border-ink-500/40 hover:bg-ink-600/40"
              >
                <td className="px-3 py-1.5 font-display text-sm font-bold text-chalk">
                  {p.ticker}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-chalk">
                  {formatQty(p.quantity)}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-muted">
                  {formatPrice(p.avg_cost)}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-chalk">
                  {formatPrice(p.livePrice)}
                </td>
                <td
                  data-testid={`pnl-${p.ticker}`}
                  className={`px-3 py-1.5 text-right tabular-nums font-semibold ${changeClass(p.livePnl)}`}
                >
                  {formatSignedUsd(p.livePnl)}
                </td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${changeClass(p.livePnlPct)}`}>
                  {formatPct(p.livePnlPct)}
                </td>
              </tr>
            ))}
            {positions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-xs text-muted">
                  No open positions. Buy something below.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
