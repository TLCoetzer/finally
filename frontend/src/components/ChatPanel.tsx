"use client";

// AI chat panel (PLAN.md §10): collapsible sidebar, scrolling history, loading
// indicator while waiting for the LLM, and inline confirmations of any trades
// and watchlist changes the assistant executed.
import { useEffect, useRef, useState } from "react";
import type { ChatLine } from "@/lib/types";

interface Props {
  lines: ChatLine[];
  loading: boolean;
  collapsed: boolean;
  onToggle: () => void;
  onSend: (message: string) => void;
}

export function ChatPanel({ lines, loading, collapsed, onToggle, onSend }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines, loading]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    onSend(text);
    setInput("");
  }

  if (collapsed) {
    return (
      <button
        type="button"
        data-testid="chat-toggle"
        onClick={onToggle}
        className="panel flex h-full w-12 flex-col items-center justify-center gap-2 text-muted hover:text-chalk"
        aria-label="Open AI assistant"
      >
        <span className="font-display text-[11px] font-bold uppercase tracking-[0.2em] [writing-mode:vertical-rl]">
          AI Copilot
        </span>
      </button>
    );
  }

  return (
    <section className="panel flex h-full flex-col" data-testid="chat-panel">
      <div className="panel-head">
        <h2 className="panel-title">AI Copilot</h2>
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          className="text-muted hover:text-chalk"
          aria-label="Collapse AI assistant"
        >
          ›
        </button>
      </div>

      <div
        ref={scrollRef}
        data-testid="chat-messages"
        className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3 py-3"
      >
        {lines.length === 0 && (
          <p className="text-xs text-muted">
            Ask FinAlly to analyze your portfolio, suggest trades, or manage your
            watchlist.
          </p>
        )}
        {lines.map((line) => (
          <ChatBubble key={line.id} line={line} />
        ))}
        {loading && (
          <div data-testid="chat-loading" className="flex items-center gap-1.5 px-1">
            <Dot /> <Dot delay={0.15} /> <Dot delay={0.3} />
            <span className="ml-1 text-[10px] uppercase tracking-wider text-muted">
              thinking
            </span>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex items-center gap-2 border-t border-ink-500/60 px-3 py-2.5">
        <input
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message FinAlly…"
          aria-label="Message FinAlly"
          className="field w-full"
        />
        <button
          type="submit"
          data-testid="chat-send"
          disabled={loading || !input.trim()}
          className="btn btn-submit"
        >
          Send
        </button>
      </form>
    </section>
  );
}

function ChatBubble({ line }: { line: ChatLine }) {
  const isUser = line.role === "user";
  return (
    <div
      data-testid={`chat-line-${line.role}`}
      className={`max-w-[92%] rounded-lg px-3 py-2 text-sm leading-snug ${
        isUser
          ? "ml-auto bg-brand-blue/15 text-chalk"
          : "mr-auto bg-ink-600/60 text-chalk"
      }`}
    >
      <p className="whitespace-pre-wrap">{line.content}</p>

      {line.actions && line.actions.length > 0 && (
        <div className="mt-2 space-y-1 border-t border-ink-500/50 pt-2">
          {line.actions.map((a, i) => {
            const isTrade = a.kind === "trade";
            // testid distinguishes trade vs watchlist confirmations for E2E.
            const testid = isTrade ? "chat-trade-confirm" : "chat-watchlist-confirm";
            const okColor = isTrade ? "text-up" : "text-brand-blue";
            return (
              <div
                key={i}
                data-testid={testid}
                data-ok={a.ok}
                className={`text-[11px] ${a.ok ? okColor : "text-down"}`}
              >
                {a.ok || !a.detail ? a.summary : `${a.summary} — ${a.detail}`}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Dot({ delay = 0 }: { delay?: number }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 rounded-full bg-muted animate-pulsedot"
      style={{ animationDelay: `${delay}s` }}
    />
  );
}
