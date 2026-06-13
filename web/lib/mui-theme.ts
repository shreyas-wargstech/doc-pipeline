import { createTheme, type Theme } from "@mui/material/styles";

const rgb = (r: number, g: number, b: number) => `rgb(${r} ${g} ${b})`;

// Mirrors :root in web/app/globals.css
const lightTokens = {
  background: rgb(248, 250, 252),
  foreground: rgb(30, 58, 138),
  card: rgb(255, 255, 255),
  primary: rgb(30, 64, 175),
  onPrimary: rgb(255, 255, 255),
  secondary: rgb(59, 130, 246),
  mutedFg: rgb(71, 85, 105),
  border: rgb(219, 234, 254),
  destructive: rgb(220, 38, 38),
  ok: rgb(15, 96, 48),
  warn: rgb(146, 64, 10),
  danger: rgb(185, 28, 28),
  info: rgb(67, 56, 202),
};

// Mirrors .dark in web/app/globals.css
const darkTokens = {
  background: rgb(11, 18, 32),
  foreground: rgb(226, 232, 240),
  card: rgb(19, 28, 46),
  primary: rgb(59, 130, 246),
  onPrimary: rgb(11, 18, 32),
  secondary: rgb(96, 165, 250),
  mutedFg: rgb(148, 163, 184),
  border: rgb(30, 42, 68),
  destructive: rgb(248, 113, 113),
  ok: rgb(74, 222, 128),
  warn: rgb(251, 191, 36),
  danger: rgb(248, 113, 113),
  info: rgb(165, 180, 252),
};

function buildTheme(mode: "light" | "dark"): Theme {
  const t = mode === "light" ? lightTokens : darkTokens;
  return createTheme({
    palette: {
      mode,
      primary: { main: t.primary, contrastText: t.onPrimary },
      secondary: { main: t.secondary },
      error: { main: t.destructive },
      warning: { main: t.warn },
      success: { main: t.ok },
      info: { main: t.info },
      background: { default: t.background, paper: t.card },
      text: { primary: t.foreground, secondary: t.mutedFg },
      divider: t.border,
    },
    typography: {
      fontFamily: "var(--font-sans), system-ui, sans-serif",
    },
    shape: { borderRadius: 8 },
  });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");
