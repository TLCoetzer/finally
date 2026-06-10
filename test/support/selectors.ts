/**
 * data-testid contract for the FinAlly frontend, matched to the shipped
 * components in frontend/src/components/*. Per-ticker elements use a
 * SUFFIXED testid (e.g. `watchlist-row-AAPL`), not a data-ticker attribute.
 *
 * This is the single source of truth the E2E suite uses to locate UI elements;
 * if the frontend's testids change, update only this file.
 */

export const sel = {
  // Header (Header.tsx)
  totalValue: '[data-testid="header-total-value"]',
  cashBalance: '[data-testid="header-cash"]',
  marketSource: '[data-testid="market-source"]',
  connectionDot: '[data-testid="connection-dot"]',

  // Watchlist (Watchlist.tsx / WatchlistRow.tsx)
  watchlist: '[data-testid="watchlist-panel"]',
  watchlistRow: (t: string) => `[data-testid="watchlist-row-${t.toUpperCase()}"]`,
  watchlistRowAny: '[data-testid^="watchlist-row-"]',
  watchlistPrice: (t: string) => `[data-testid="price-${t.toUpperCase()}"]`,
  watchlistChangePct: (t: string) => `[data-testid="change-${t.toUpperCase()}"]`,
  watchlistRemove: (t: string) => `[data-testid="remove-${t.toUpperCase()}"]`,
  watchlistAddInput: '[data-testid="watchlist-add-input"]',
  watchlistAddButton: '[data-testid="watchlist-add-button"]',
  watchlistError: '[data-testid="watchlist-error"]',

  // Positions table (PositionsTable.tsx). Only the row and the P&L cell carry
  // testids; other cells are positional (cellIndex via the row's <td>s).
  positionsTable: '[data-testid="positions-panel"]',
  positionRow: (t: string) => `[data-testid="position-row-${t.toUpperCase()}"]`,
  positionRowAny: '[data-testid^="position-row-"]',
  positionPnl: (t: string) => `[data-testid="pnl-${t.toUpperCase()}"]`,

  // Portfolio heatmap / treemap (Heatmap.tsx). Cells are SVG <g> groups.
  heatmap: '[data-testid="heatmap-panel"]',
  heatmapCell: (t: string) => `[data-testid="heatmap-cell-${t.toUpperCase()}"]`,

  // Trade bar (TradeBar.tsx)
  tradeBar: '[data-testid="trade-bar"]',
  tradeTicker: '[data-testid="trade-ticker"]',
  tradeQuantity: '[data-testid="trade-qty"]',
  tradeBuy: '[data-testid="trade-buy"]',
  tradeSell: '[data-testid="trade-sell"]',
  tradeMessage: '[data-testid="trade-message"]',

  // AI chat (ChatPanel.tsx). The panel may start collapsed -> chat-toggle.
  chatPanel: '[data-testid="chat-panel"]',
  chatToggle: '[data-testid="chat-toggle"]',
  chatInput: '[data-testid="chat-input"]',
  chatSend: '[data-testid="chat-send"]',
  chatMessages: '[data-testid="chat-messages"]',
  chatLoading: '[data-testid="chat-loading"]',
  chatMessageUser: '[data-testid="chat-line-user"]',
  chatMessageAssistant: '[data-testid="chat-line-assistant"]',
  chatTradeConfirm: '[data-testid="chat-trade-confirm"]',
  chatWatchlistConfirm: '[data-testid="chat-watchlist-confirm"]',

  // Main chart (ChartPanel)
  mainChart: '[data-testid="main-chart"]',
} as const;

/**
 * Connection-dot state. The dot exposes EventSource.readyState via `data-conn`
 * (ConnectionDot.tsx): OPEN→"open" (green), CONNECTING→"connecting" (yellow),
 * CLOSED→"closed" (red). We assert this attribute rather than a CSS color.
 */
export const ConnectionState = {
  attr: "data-conn",
  connected: "open",
  connecting: "connecting",
  disconnected: "closed",
} as const;
