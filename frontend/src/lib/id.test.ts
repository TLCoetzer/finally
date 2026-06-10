import { afterEach, describe, expect, it, vi } from "vitest";
import { uid } from "./id";

describe("uid", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses crypto.randomUUID when available (secure context)", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "fixed-uuid" });
    expect(uid()).toBe("fixed-uuid");
  });

  it("falls back to a unique id when randomUUID is missing (insecure http context)", () => {
    // Simulate plain-HTTP access where crypto.randomUUID is undefined.
    vi.stubGlobal("crypto", {});
    const a = uid();
    const b = uid();
    expect(a).not.toBe(b);
    expect(a.length).toBeGreaterThan(0);
  });

  it("falls back when crypto itself is undefined", () => {
    vi.stubGlobal("crypto", undefined);
    expect(() => uid()).not.toThrow();
  });
});
