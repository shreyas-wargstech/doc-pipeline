import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--color-background)",
        foreground: "var(--color-foreground)",
        primary: { DEFAULT: "var(--color-primary)", fg: "var(--color-on-primary)" },
        secondary: "var(--color-secondary)",
        accent: "var(--color-accent)",
        muted: { DEFAULT: "var(--color-muted)", fg: "var(--color-muted-fg)" },
        border: "var(--color-border)",
        card: "var(--color-card)",
        destructive: "var(--color-destructive)",
        ring: "var(--color-ring)",
        ok: "var(--color-ok)",
        warn: "var(--color-warn)",
        danger: "var(--color-danger)",
        info: "var(--color-info)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
