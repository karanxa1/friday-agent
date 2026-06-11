import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: {
          DEFAULT: "#181818",
          sidebar: "#141414",
          editor: "#1e1e1e",
          elevated: "#202020",
          hover: "#2a2a2a",
          active: "#323232",
        },
        ink: {
          DEFAULT: "#e6e6e6",
          secondary: "#a8a8a8",
          muted: "#6e6e6e",
        },
        edge: {
          subtle: "#2b2b2b",
          strong: "#3a3a3a",
        },
        accent: {
          DEFAULT: "#4daafc",
          hover: "#6cb8fd",
        },
        state: {
          ok: "#3fb950",
          run: "#d9a23a",
          err: "#f85149",
        },
        diff: {
          addbg: "rgba(63,185,80,0.15)",
          addtext: "#7ee787",
          rmbg: "rgba(248,81,73,0.15)",
          rmtext: "#ffa198",
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'Segoe UI', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        caret: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.2" },
        },
        progress: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(250%)" },
        },
        pulsedot: {
          "0%,100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.4", transform: "scale(0.8)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.5s linear infinite",
        caret: "caret 1.1s ease-in-out infinite",
        progress: "progress 1.4s ease-in-out infinite",
        pulsedot: "pulsedot 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
