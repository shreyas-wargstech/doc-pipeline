import { createTheme, type Theme } from "@mui/material/styles";
import { rgb, shadows as warm, radii } from "./tokens";

const DISPLAY = "var(--font-display), Georgia, serif";
const SANS = "var(--font-sans), system-ui, sans-serif";

// MUI requires a 25-length shadow array. Map our warm scale onto the
// commonly-used low elevations; reuse `lg` for the rest.
const shadowScale = Array.from({ length: 25 }, (_, i) => {
  if (i === 0) return "none";
  if (i === 1) return warm.sm;
  if (i === 2) return warm.md;
  if (i <= 8) return warm.lg;
  return warm.xl;
}) as Theme["shadows"];

export const theme: Theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: rgb("primary"), dark: rgb("primary-hover"), contrastText: rgb("on-primary") },
    secondary: { main: rgb("primary-hover") },
    error: { main: rgb("danger") },
    warning: { main: rgb("warn") },
    success: { main: rgb("success") },
    info: { main: rgb("info") },
    background: { default: rgb("background"), paper: rgb("surface") },
    text: { primary: rgb("foreground"), secondary: rgb("muted-fg") },
    divider: rgb("border"),
  },
  shape: { borderRadius: radii.base },
  shadows: shadowScale,
  typography: {
    fontFamily: SANS,
    h1: { fontFamily: DISPLAY, fontWeight: 600, fontSize: "1.75rem", letterSpacing: "-0.3px" },
    h2: { fontFamily: DISPLAY, fontWeight: 600, fontSize: "1.3125rem" },
    h3: { fontFamily: SANS, fontWeight: 600, fontSize: "0.9375rem" },
    body1: { fontFamily: SANS, fontSize: "0.875rem" },
    body2: { fontFamily: SANS, fontSize: "0.8125rem" },
    button: { fontFamily: SANS, fontWeight: 600, fontSize: "0.875rem", textTransform: "none" },
    overline: { fontFamily: "var(--font-mono), ui-monospace, monospace", fontWeight: 600, fontSize: "0.65625rem", letterSpacing: "1px" },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: radii.base, textTransform: "none", fontWeight: 600 },
        containedPrimary: {
          boxShadow: warm.md,
          "&:hover": { backgroundColor: rgb("primary-hover"), boxShadow: warm.lg },
        },
        outlined: {
          borderColor: rgb("border-strong"),
          "&:hover": { borderColor: rgb("primary"), backgroundColor: rgb("primary-tint") },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
        outlined: { borderColor: rgb("border") },
      },
    },
    MuiAppBar: {
      defaultProps: { elevation: 0, color: "default" },
      styleOverrides: {
        root: { backgroundColor: rgb("surface"), borderBottom: `1px solid ${rgb("border")}` },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundColor: rgb("surface-alt"), borderRight: `1px solid ${rgb("border")}` },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          "&.Mui-selected": {
            backgroundColor: rgb("primary-tint"),
            color: rgb("primary-hover"),
            fontWeight: 600,
            "&:hover": { backgroundColor: rgb("primary-tint") },
            "& .MuiListItemIcon-root": { color: rgb("primary-hover") },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: radii.pill, fontWeight: 600 },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: radii.base,
          backgroundColor: rgb("surface"),
          "& .MuiOutlinedInput-notchedOutline": { borderColor: rgb("border-strong") },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: rgb("primary"), borderWidth: 1 },
          "&.Mui-focused": { boxShadow: "0 0 0 4px rgba(13,148,136,.14)" },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: rgb("border") },
        head: { fontWeight: 600, color: rgb("muted-fg") },
      },
    },
    MuiDivider: { styleOverrides: { root: { borderColor: rgb("border") } } },
  },
});
