import type { Config } from "tailwindcss";

const c = (name: string) => `rgb(var(--color-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: c("background"),
        foreground: c("foreground"),
        surface: c("surface"),
        "surface-alt": c("surface-alt"),
        card: c("surface"),
        primary: { DEFAULT: c("primary"), fg: c("on-primary"), hover: c("primary-hover"), tint: c("primary-tint") },
        muted: { DEFAULT: c("surface-alt"), fg: c("muted-fg") },
        "tertiary-fg": c("tertiary-fg"),
        border: { DEFAULT: c("border"), strong: c("border-strong") },
        destructive: c("danger"),
        ring: c("primary"),
        ok: c("ok"),
        warn: c("warn"),
        danger: c("danger"),
        info: c("info"),
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  safelist: ["text-foreground", "text-ok", "text-warn", "text-danger", "text-info"],
  plugins: [],
};
export default config;
