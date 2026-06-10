"use client";

// Portfolio heatmap (PLAN.md §10): a treemap where each rectangle is a position
// sized by portfolio weight (market value) and colored by P&L % (green profit,
// red loss). Built on Recharts Treemap with a custom cell renderer.
import { ResponsiveContainer, Treemap } from "recharts";
import { formatPct } from "@/lib/format";
import type { LivePosition } from "@/lib/portfolio";

interface Props {
  positions: LivePosition[];
}

// Map P&L % to a fill: saturated green/red scaled by magnitude, neutral at 0.
function pnlFill(pct: number): string {
  const mag = Math.min(Math.abs(pct) / 10, 1); // saturate at +/-10%
  const alpha = 0.18 + mag * 0.6;
  return pct >= 0
    ? `rgba(27,196,125,${alpha.toFixed(2)})`
    : `rgba(240,80,110,${alpha.toFixed(2)})`;
}

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPct?: number;
}

function Cell(props: CellProps) {
  const { x = 0, y = 0, width = 0, height = 0, name, pnlPct = 0 } = props;
  const showText = width > 46 && height > 26;
  return (
    <g data-testid={name ? `heatmap-cell-${name}` : undefined}>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={pnlFill(pnlPct)}
        stroke="#0d1117"
        strokeWidth={2}
        rx={3}
      />
      {showText && (
        <>
          <text
            x={x + 6}
            y={y + 16}
            fill="#e6edf6"
            fontSize={12}
            fontWeight={700}
            className="font-display"
          >
            {name}
          </text>
          <text x={x + 6} y={y + 30} fill="#e6edf6" fontSize={10} opacity={0.85}>
            {formatPct(pnlPct)}
          </text>
        </>
      )}
    </g>
  );
}

export function Heatmap({ positions }: Props) {
  const data = positions
    .filter((p) => p.liveValue > 0)
    .map((p) => ({
      name: p.ticker,
      size: p.liveValue,
      pnlPct: p.livePnlPct,
    }));

  return (
    <section className="panel flex h-full flex-col" data-testid="heatmap-panel">
      <div className="panel-head">
        <h2 className="panel-title">Allocation Heatmap</h2>
        <span className="text-[10px] text-muted">by weight · P&L</span>
      </div>
      <div className="min-h-0 flex-1 p-2">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-muted">
            No positions to map.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              isAnimationActive={false}
              content={<Cell />}
            />
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
