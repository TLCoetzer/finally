"use client";

// Tiny SVG sparkline accumulated from the SSE stream (PLAN.md §10). Hand-rolled
// SVG (no chart lib) so it stays cheap to render for every watchlist row.
import type { PricePoint } from "@/lib/types";

interface Props {
  points: PricePoint[];
  width?: number;
  height?: number;
  positive?: boolean;
}

export function Sparkline({ points, width = 76, height = 24, positive }: Props) {
  if (points.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="sparkline"
        data-testid="sparkline-empty"
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#232d42"
          strokeWidth={1}
        />
      </svg>
    );
  }

  const prices = points.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const stepX = width / (points.length - 1);

  const color = positive ? "#1bc47d" : "#f0506e";
  const d = points
    .map((p, i) => {
      const x = i * stepX;
      const y = height - ((p.price - min) / span) * (height - 2) - 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label="sparkline"
      data-testid="sparkline"
    >
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}
