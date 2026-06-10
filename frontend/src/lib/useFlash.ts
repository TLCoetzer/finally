"use client";

// Returns a one-shot animation class when `value` moves up or down, then clears
// it after the flash duration so the CSS animation can re-trigger (PLAN.md §10).
import { useEffect, useRef, useState } from "react";

export type FlashClass = "" | "animate-flashup" | "animate-flashdown";

export function useFlash(value: number | null | undefined, duration = 500): FlashClass {
  const prev = useRef<number | null | undefined>(value);
  const [flash, setFlash] = useState<FlashClass>("");

  useEffect(() => {
    const before = prev.current;
    prev.current = value;
    if (
      before === null ||
      before === undefined ||
      value === null ||
      value === undefined ||
      value === before
    ) {
      return;
    }
    setFlash(value > before ? "animate-flashup" : "animate-flashdown");
    const id = setTimeout(() => setFlash(""), duration);
    return () => clearTimeout(id);
  }, [value, duration]);

  return flash;
}
