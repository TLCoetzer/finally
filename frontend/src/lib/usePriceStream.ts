"use client";

// Owns the single EventSource to /api/stream/prices (PLAN.md §6/§10).
// Exposes: latest quote per ticker, accumulated history per ticker (for
// sparklines + main chart), and the connection state derived from
// EventSource.readyState (OPEN→green, CONNECTING→yellow, CLOSED→red).
import { useEffect, useRef, useState } from "react";
import type { PriceFrame, PricePoint } from "./types";

export type ConnState = "open" | "connecting" | "closed";

const MAX_POINTS = 600; // cap accumulated history per ticker (~5min @ 500ms)

export interface PriceStream {
  quotes: Record<string, PriceFrame>;
  history: Record<string, PricePoint[]>;
  conn: ConnState;
}

function readyStateToConn(rs: number): ConnState {
  // EventSource: 0 CONNECTING, 1 OPEN, 2 CLOSED.
  if (rs === EventSource.OPEN) return "open";
  if (rs === EventSource.CLOSED) return "closed";
  return "connecting";
}

export function usePriceStream(path = "/api/stream/prices"): PriceStream {
  const [quotes, setQuotes] = useState<Record<string, PriceFrame>>({});
  const [conn, setConn] = useState<ConnState>("connecting");
  // History is held in a ref and mirrored to state on a throttle so chart
  // re-renders stay cheap even at 500ms tick rate across many tickers.
  const historyRef = useRef<Record<string, PricePoint[]>>({});
  const [history, setHistory] = useState<Record<string, PricePoint[]>>({});

  useEffect(() => {
    const es = new EventSource(path);
    let flushTimer: ReturnType<typeof setInterval> | null = null;
    let dirty = false;

    const syncConn = () => setConn(readyStateToConn(es.readyState));

    es.onopen = syncConn;

    es.onmessage = (ev: MessageEvent) => {
      let frame: PriceFrame;
      try {
        frame = JSON.parse(ev.data) as PriceFrame;
      } catch {
        return;
      }
      if (!frame?.ticker) return;

      setQuotes((prev) => ({ ...prev, [frame.ticker]: frame }));

      const arr = historyRef.current[frame.ticker] ?? [];
      arr.push({ t: frame.timestamp * 1000, price: frame.price });
      if (arr.length > MAX_POINTS) arr.shift();
      historyRef.current[frame.ticker] = arr;
      dirty = true;
    };

    es.onerror = () => {
      // EventSource auto-reconnects; reflect the live readyState in the dot.
      syncConn();
    };

    // Mirror accumulated history to state at ~1s so charts update smoothly
    // without re-rendering on every individual frame.
    flushTimer = setInterval(() => {
      if (!dirty) return;
      dirty = false;
      setHistory(
        Object.fromEntries(
          Object.entries(historyRef.current).map(([k, v]) => [k, v.slice()]),
        ),
      );
    }, 1000);

    // Poll readyState so the dot reflects CONNECTING during silent retries.
    const connPoll = setInterval(syncConn, 1000);

    return () => {
      if (flushTimer) clearInterval(flushTimer);
      clearInterval(connPoll);
      es.close();
    };
  }, [path]);

  return { quotes, history, conn };
}
