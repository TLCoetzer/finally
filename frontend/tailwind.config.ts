import type { Config } from "tailwindcss";

// FinAlly terminal palette (PLAN.md §2). Dark, data-dense, no pure black.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Surfaces — layered slate/ink, never #000.
        ink: {
          900: "#0a0e16", // app background floor
          800: "#0d1117", // primary panel background
          700: "#121826", // raised panel
          600: "#1a2233", // hover / inset
          500: "#232d42", // borders, dividers
        },
        // Brand accents (PLAN.md §2 color scheme).
        brand: {
          yellow: "#ecad0a",
          blue: "#209dd7",
          purple: "#753991",
        },
        // Market semantics.
        up: "#1bc47d",
        down: "#f0506e",
        muted: "#7b8aa3",
        chalk: "#e6edf6",
      },
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(32,157,215,0.4), 0 0 24px -6px rgba(32,157,215,0.5)",
      },
      keyframes: {
        flashup: {
          "0%": { backgroundColor: "rgba(27,196,125,0.35)" },
          "100%": { backgroundColor: "rgba(27,196,125,0)" },
        },
        flashdown: {
          "0%": { backgroundColor: "rgba(240,80,110,0.35)" },
          "100%": { backgroundColor: "rgba(240,80,110,0)" },
        },
        fadein: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulsedot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        flashup: "flashup 500ms ease-out",
        flashdown: "flashdown 500ms ease-out",
        fadein: "fadein 240ms ease-out both",
        pulsedot: "pulsedot 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
