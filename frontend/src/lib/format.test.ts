import { describe, expect, it } from "vitest";
import {
  changeClass,
  formatPct,
  formatPrice,
  formatQty,
  formatSignedUsd,
  formatUsd,
} from "./format";

describe("format helpers", () => {
  it("formats prices to two decimals", () => {
    expect(formatPrice(190.4)).toBe("190.40");
    expect(formatPrice(1234.5)).toBe("1,234.50");
  });

  it("renders -- for missing values", () => {
    expect(formatPrice(null)).toBe("--");
    expect(formatUsd(undefined)).toBe("--");
    expect(formatPct(null)).toBe("--");
    expect(formatQty(NaN)).toBe("--");
  });

  it("prefixes usd and signs", () => {
    expect(formatUsd(10)).toBe("$10.00");
    expect(formatSignedUsd(5)).toBe("+$5.00");
    expect(formatSignedUsd(-5)).toBe("-$5.00");
  });

  it("signs percentages", () => {
    expect(formatPct(2.5)).toBe("+2.50%");
    expect(formatPct(-1.2)).toBe("-1.20%");
    expect(formatPct(0)).toBe("0.00%");
  });

  it("trims fractional share trailing zeros", () => {
    expect(formatQty(10)).toBe("10");
    expect(formatQty(2.5)).toBe("2.5");
    expect(formatQty(1.2500)).toBe("1.25");
  });

  it("maps change sign to color class", () => {
    expect(changeClass(1)).toBe("text-up");
    expect(changeClass(-1)).toBe("text-down");
    expect(changeClass(0)).toBe("text-muted");
    expect(changeClass(null)).toBe("text-muted");
  });
});
