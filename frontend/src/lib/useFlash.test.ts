import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useFlash } from "./useFlash";

describe("useFlash", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("flashes up when the value increases", () => {
    const { result, rerender } = renderHook(({ v }) => useFlash(v), {
      initialProps: { v: 100 },
    });
    expect(result.current).toBe("");
    rerender({ v: 101 });
    expect(result.current).toBe("animate-flashup");
  });

  it("flashes down when the value decreases", () => {
    const { result, rerender } = renderHook(({ v }) => useFlash(v), {
      initialProps: { v: 100 },
    });
    rerender({ v: 99 });
    expect(result.current).toBe("animate-flashdown");
  });

  it("clears the flash class after the duration", () => {
    const { result, rerender } = renderHook(({ v }) => useFlash(v, 500), {
      initialProps: { v: 100 },
    });
    rerender({ v: 105 });
    expect(result.current).toBe("animate-flashup");
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(result.current).toBe("");
  });

  it("does not flash when the value is unchanged", () => {
    const { result, rerender } = renderHook(({ v }) => useFlash(v), {
      initialProps: { v: 100 },
    });
    rerender({ v: 100 });
    expect(result.current).toBe("");
  });
});
