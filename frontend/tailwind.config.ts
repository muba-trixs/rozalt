import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("background"),
        sidebar: v("sidebar"),
        surface: v("surface"),
        elevated: v("surface-elevated"),
        border: v("border"),
        fg: v("text-primary"),
        muted: v("text-secondary"),
        subtle: v("text-muted"),
        accent: v("accent-blue"),
        positive: v("positive"),
        negative: v("negative"),
        warning: v("warning"),
        cyan: v("analytical-cyan"),
      },
      fontFamily: {
        sans: ["'Inter Variable'", "Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: { "2xs": ["10px", "14px"], xs: ["11px", "16px"], sm: ["12px", "18px"], base: ["13px", "20px"] },
      borderRadius: { DEFAULT: "4px", sm: "3px", md: "4px", lg: "6px" },
      transitionDuration: { DEFAULT: "140ms" },
    },
  },
  plugins: [],
} satisfies Config;
