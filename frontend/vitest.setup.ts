import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// Recharts' ResponsiveContainer needs a measurable box; jsdom reports 0.
// Stub a fixed size so charts render in tests.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
  configurable: true,
  value: 600,
});
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
  configurable: true,
  value: 400,
});

// Recharts' ResponsiveContainer measures via getBoundingClientRect; jsdom
// returns zeros, which collapses the chart and unmounts its children.
HTMLElement.prototype.getBoundingClientRect = function () {
  return {
    width: 600,
    height: 400,
    top: 0,
    left: 0,
    right: 600,
    bottom: 400,
    x: 0,
    y: 0,
    toJSON() {},
  } as DOMRect;
};

// jsdom elements have no scrollTo; the chat panel auto-scrolls on new messages.
HTMLElement.prototype.scrollTo =
  HTMLElement.prototype.scrollTo || (() => undefined);

// crypto.randomUUID for jsdom environments that lack it.
if (!globalThis.crypto?.randomUUID) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis.crypto as any).randomUUID = () =>
    "test-" + Math.random().toString(36).slice(2);
}

// jsdom has no EventSource; provide a no-op stub for components that mount it.
if (typeof globalThis.EventSource === "undefined") {
  class FakeEventSource {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readonly CONNECTING = 0;
    readonly OPEN = 1;
    readonly CLOSED = 2;
    readyState = 0;
    onopen: ((ev: Event) => void) | null = null;
    onmessage: ((ev: MessageEvent) => void) | null = null;
    onerror: ((ev: Event) => void) | null = null;
    constructor(public url: string) {}
    close() {
      this.readyState = 2;
    }
  }
  globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
}
