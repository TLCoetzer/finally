"use client";

// Top bar: brand, live total value, cash, market source, connection dot.
import { ConnectionDot } from "./ConnectionDot";
import type { ConnState } from "@/lib/usePriceStream";
import { formatUsd } from "@/lib/format";

interface Props {
  totalValue: number;
  cash: number;
  source?: string;
  conn: ConnState;
}

export function Header({ totalValue, cash, source, conn }: Props) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-ink-500/70 bg-ink-800/70 px-4 py-2.5 backdrop-blur">
      <div className="flex items-baseline gap-2">
        <span className="font-display text-lg font-extrabold tracking-tight text-chalk">
          Fin<span className="text-brand-yellow">Ally</span>
        </span>
        <span className="hidden text-[10px] uppercase tracking-[0.3em] text-muted sm:inline">
          AI Trading Desk
        </span>
      </div>

      <div className="flex items-center gap-5">
        <Stat label="Total Value">
          <span data-testid="header-total-value" className="text-base font-bold text-chalk">
            {formatUsd(totalValue)}
          </span>
        </Stat>
        <div className="hidden h-7 w-px bg-ink-500/70 sm:block" />
        <Stat label="Cash">
          <span data-testid="header-cash" className="text-base font-semibold text-brand-blue">
            {formatUsd(cash)}
          </span>
        </Stat>
        <div className="hidden h-7 w-px bg-ink-500/70 md:block" />
        {source && (
          <Stat label="Feed">
            <span data-testid="market-source" className="text-xs uppercase tracking-wider text-muted">
              {source}
            </span>
          </Stat>
        )}
        <ConnectionDot conn={conn} />
      </div>
    </header>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[9px] uppercase tracking-[0.2em] text-muted/70">{label}</span>
      {children}
    </div>
  );
}
