"use client";

// Larger chart for the selected ticker. The series accumulates from the SSE
// stream since page load (no history endpoint, PLAN.md §10), so it fills in
// progressively.
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatPct, formatPrice } from "@/lib/format";
import type { PriceFrame, PricePoint } from "@/lib/types";

interface Props {
  ticker: string | null;
  frame?: PriceFrame;
  history: PricePoint[];
}

export function MainChart({ ticker, frame, history }: Props) {
  const positive = (frame?.change_pct ?? 0) >= 0;
  const stroke = positive ? "#1bc47d" : "#f0506e";

  const data = history.map((p) => ({
    t: p.t,
    price: p.price,
    label: new Date(p.t).toLocaleTimeString("en-US", {
      hour12: false,
      minute: "2-digit",
      second: "2-digit",
    }),
  }));

  return (
    <section className="panel flex h-full flex-col" data-testid="main-chart">
      <div className="panel-head">
        <div className="flex items-baseline gap-3">
          <h2 className="panel-title">Chart</h2>
          {ticker && (
            <span className="font-display text-base font-bold text-chalk">{ticker}</span>
          )}
        </div>
        {frame && (
          <div className="flex items-baseline gap-3 tabular-nums">
            <span className="text-base font-bold text-chalk">{formatPrice(frame.price)}</span>
            <span className={`text-xs font-semibold ${positive ? "text-up" : "text-down"}`}>
              {formatPct(frame.change_pct)}
            </span>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 p-2">
        {data.length < 2 ? (
          <div className="flex h-full items-center justify-center text-xs text-muted">
            {ticker ? "Accumulating price history…" : "Select a ticker to chart"}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="label"
                tick={{ fill: "#7b8aa3", fontSize: 10 }}
                axisLine={{ stroke: "#232d42" }}
                tickLine={false}
                minTickGap={48}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: "#7b8aa3", fontSize: 10 }}
                axisLine={{ stroke: "#232d42" }}
                tickLine={false}
                width={56}
                tickFormatter={(v: number) => formatPrice(v)}
                orientation="right"
              />
              <Tooltip
                contentStyle={{
                  background: "#0d1117",
                  border: "1px solid #232d42",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#7b8aa3" }}
                formatter={(v: number) => [formatPrice(v), "Price"]}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke={stroke}
                strokeWidth={1.8}
                fill="url(#chartFill)"
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
