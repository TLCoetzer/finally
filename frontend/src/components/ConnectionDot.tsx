"use client";

// Connection status dot mapping EventSource.readyState (PLAN.md §10):
// OPEN→green, CONNECTING→yellow, CLOSED→red.
import type { ConnState } from "@/lib/usePriceStream";

const MAP: Record<ConnState, { color: string; label: string }> = {
  open: { color: "bg-up", label: "Live" },
  connecting: { color: "bg-brand-yellow", label: "Connecting" },
  closed: { color: "bg-down", label: "Disconnected" },
};

export function ConnectionDot({ conn }: { conn: ConnState }) {
  const { color, label } = MAP[conn];
  return (
    <div
      className="flex items-center gap-1.5"
      data-testid="connection-dot"
      data-conn={conn}
      title={label}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${color} ${
          conn !== "open" ? "animate-pulsedot" : ""
        }`}
      />
      <span className="text-[10px] uppercase tracking-wider text-muted">{label}</span>
    </div>
  );
}
