import type { Config } from "tailwindcss";

const c = (name: string) => `rgb(var(--color-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: c("background"),
        foreground: c("foreground"),
        surface: { DEFAULT: c("surface"), hover: c("surface-hover"), alt: c("surface-alt") },
        card: { DEFAULT: c("surface"), foreground: c("foreground") },
        primary: { DEFAULT: c("primary"), foreground: c("on-primary"), hover: c("primary-hover"), tint: c("primary-tint") },
        secondary: { DEFAULT: c("secondary"), foreground: c("on-secondary"), hover: c("secondary-hover"), tint: c("secondary-tint") },
        muted: { DEFAULT: c("surface-alt"), foreground: c("muted-fg") },
        accent: { DEFAULT: c("surface-hover"), foreground: c("foreground") },
        destructive: { DEFAULT: c("danger"), foreground: c("on-primary") },
        "tertiary-fg": c("tertiary-fg"),
        border: { DEFAULT: c("border"), strong: c("border-strong"), input: c("border-strong") },
        input: c("border-strong"),
        ring: c("primary"),
        ok: c("ok"),
        "ok-bg": c("ok-bg"),
        success: c("success"),
        "success-bg": c("success-bg"),
        warn: c("warn"),
        danger: c("danger"),
        info: c("info"),
        popover: { DEFAULT: c("surface"), foreground: c("foreground") },
      },
      fontFamily: {
        display: ["var(--font-geist)", "system-ui", "sans-serif"],
        sans: ["var(--font-geist)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        sm: "0 1px 2px rgba(60,45,25,0.04)",
        md: "0 4px 12px -4px rgba(60,45,25,0.10)",
        lg: "0 10px 30px -12px rgba(60,45,25,0.16)",
        xl: "0 24px 60px -24px rgba(60,45,25,0.28)",
      },
      borderRadius: {
        base: "8px",
        panel: "12px",
        pill: "24px",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 2s linear infinite",
        "fade-in": "fade-in 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards",
      },
    },
  },
  safelist: ["text-foreground", "text-ok", "text-warn", "text-danger", "text-info"],
  plugins: [],
};
export default config;
