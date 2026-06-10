"use client";

// FinAlly trading workstation — single-page terminal (PLAN.md §10). Wires the
// SSE price stream to every panel and owns portfolio/watchlist/chat state.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Header } from "@/components/Header";
import { Watchlist } from "@/components/Watchlist";
import { MainChart } from "@/components/MainChart";
import { Heatmap } from "@/components/Heatmap";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeBar } from "@/components/TradeBar";
import { ChatPanel } from "@/components/ChatPanel";
import { usePriceStream } from "@/lib/usePriceStream";
import { liveTotalValue, livePositions } from "@/lib/portfolio";
import { api } from "@/lib/api";
import { uid } from "@/lib/id";
import type {
  ChatLine,
  PortfolioResponse,
  TradeSide,
  TradeResponse,
} from "@/lib/types";

export default function Page() {
  const { quotes, history, conn } = usePriceStream();

  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioResponse>({
    cash: 0,
    positions: [],
    total_value: 0,
  });
  const [source, setSource] = useState<string>();
  const [selected, setSelected] = useState<string | null>(null);

  const [chatLines, setChatLines] = useState<ChatLine[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);

  // ---- data loaders ------------------------------------------------------
  const refreshWatchlist = useCallback(async () => {
    const res = await api.getWatchlist();
    const tickers = res.tickers.map((t) => t.ticker);
    setWatchlist(tickers);
    setSelected((cur) => cur ?? tickers[0] ?? null);
  }, []);

  const refreshPortfolio = useCallback(async () => {
    setPortfolio(await api.getPortfolio());
  }, []);

  useEffect(() => {
    void refreshWatchlist();
    void refreshPortfolio();
    api.health().then((h) => setSource(h.source)).catch(() => {});
  }, [refreshWatchlist, refreshPortfolio]);

  // ---- derived -----------------------------------------------------------
  const positions = useMemo(
    () => livePositions(portfolio.positions, quotes),
    [portfolio.positions, quotes],
  );
  const totalValue = useMemo(
    () => liveTotalValue(portfolio.cash, portfolio.positions, quotes),
    [portfolio.cash, portfolio.positions, quotes],
  );

  // ---- handlers ----------------------------------------------------------
  const handleAdd = useCallback(
    async (ticker: string) => {
      await api.addWatchlist(ticker);
      await refreshWatchlist();
      setSelected(ticker);
    },
    [refreshWatchlist],
  );

  const handleRemove = useCallback(
    async (ticker: string) => {
      await api.removeWatchlist(ticker);
      await refreshWatchlist();
    },
    [refreshWatchlist],
  );

  const handleTrade = useCallback(
    async (ticker: string, quantity: number, side: TradeSide): Promise<TradeResponse> => {
      const res = await api.trade({ ticker, quantity, side });
      await Promise.all([refreshPortfolio(), refreshWatchlist()]);
      return res;
    },
    [refreshPortfolio, refreshWatchlist],
  );

  const handleSend = useCallback(
    async (message: string) => {
      const id = uid();
      setChatLines((prev) => [...prev, { id, role: "user", content: message }]);
      setChatLoading(true);
      try {
        const res = await api.chat(message);
        setChatLines((prev) => [
          ...prev,
          {
            id: uid(),
            role: "assistant",
            content: res.message,
            actions: res.actions,
          },
        ]);
        // The assistant may have traded or changed the watchlist — refresh both.
        await Promise.all([refreshPortfolio(), refreshWatchlist()]);
      } catch (err) {
        setChatLines((prev) => [
          ...prev,
          {
            id: uid(),
            role: "assistant",
            content:
              err instanceof Error
                ? `Sorry, I hit an error: ${err.message}`
                : "Sorry, something went wrong.",
          },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [refreshPortfolio, refreshWatchlist],
  );

  // ---- layout ------------------------------------------------------------
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Header totalValue={totalValue} cash={portfolio.cash} source={source} conn={conn} />

      <main className="grid min-h-0 flex-1 grid-cols-12 gap-3 p-3">
        {/* Left: watchlist */}
        <div className="col-span-12 min-h-0 lg:col-span-3">
          <Watchlist
            tickers={watchlist}
            quotes={quotes}
            history={history}
            selected={selected}
            onSelect={setSelected}
            onAdd={handleAdd}
            onRemove={handleRemove}
          />
        </div>

        {/* Center: chart over trade bar, then positions + heatmap */}
        <div className="col-span-12 flex min-h-0 flex-col gap-3 lg:col-span-6">
          <div className="min-h-0 flex-[3]">
            <MainChart
              ticker={selected}
              frame={selected ? quotes[selected] : undefined}
              history={selected ? history[selected] ?? [] : []}
            />
          </div>
          <TradeBar selectedTicker={selected} onTrade={handleTrade} />
          <div className="grid min-h-0 flex-[4] grid-cols-2 gap-3">
            <PositionsTable positions={positions} onSelect={setSelected} />
            <Heatmap positions={positions} />
          </div>
        </div>

        {/* Right: AI chat */}
        <div className="col-span-12 min-h-0 lg:col-span-3">
          <ChatPanel
            lines={chatLines}
            loading={chatLoading}
            collapsed={chatCollapsed}
            onToggle={() => setChatCollapsed((c) => !c)}
            onSend={handleSend}
          />
        </div>
      </main>
    </div>
  );
}
