"use client";

// One watchlist row. Price cell flashes green/red on change (PLAN.md §10),
// change % is vs the session reference price (from the SSE frame), and the
// sparkline is accumulated from the stream since page load.
import { Sparkline } from "./Sparkline";
import { useFlash } from "@/lib/useFlash";
import { changeClass, formatPct, formatPrice } from "@/lib/format";
import type { PriceFrame, PricePoint } from "@/lib/types";

interface Props {
  ticker: string;
  frame?: PriceFrame;
  history: PricePoint[];
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

export function WatchlistRow({
  ticker,
  frame,
  history,
  selected,
  onSelect,
  onRemove,
}: Props) {
  const price = frame?.price ?? null;
  const changePct = frame?.change_pct ?? null;
  const flash = useFlash(price);

  return (
    <tr
      data-testid={`watchlist-row-${ticker}`}
      data-selected={selected}
      onClick={() => onSelect(ticker)}
      className={`group cursor-pointer border-b border-ink-500/40 transition-colors ${
        selected ? "bg-brand-blue/10" : "hover:bg-ink-600/40"
      }`}
    >
      <td className="px-3 py-1.5">
        <span className="font-display text-sm font-bold tracking-wide text-chalk">
          {ticker}
        </span>
      </td>
      <td className={`px-3 py-1.5 text-right tabular-nums ${flash} rounded`}>
        <span data-testid={`price-${ticker}`} className="text-sm text-chalk">
          {formatPrice(price)}
        </span>
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums">
        <span
          data-testid={`change-${ticker}`}
          className={`text-xs font-semibold ${changeClass(changePct)}`}
        >
          {formatPct(changePct)}
        </span>
      </td>
      <td className="px-2 py-1.5">
        <div className="flex justify-end">
          <Sparkline points={history} positive={(changePct ?? 0) >= 0} />
        </div>
      </td>
      <td className="px-2 py-1.5 text-right">
        <button
          type="button"
          data-testid={`remove-${ticker}`}
          aria-label={`Remove ${ticker}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove(ticker);
          }}
          className="rounded px-1.5 text-muted opacity-0 transition-opacity hover:text-down group-hover:opacity-100"
        >
          ×
        </button>
      </td>
    </tr>
  );
}
