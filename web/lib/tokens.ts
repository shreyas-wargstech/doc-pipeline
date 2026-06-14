// Single source of truth for design tokens.
// `colorTriplets` feed the runtime CSS custom properties (Tailwind utilities).
// `rgb()` produces real color strings for the MUI theme (MUI's color
// augmentation cannot parse `var(--x)` strings, so it needs real values).

/** name -> "R G B" (space-separated, no rgb() wrapper) */
export const colorTriplets = {
  background: "251 250 247", // #FBFAF7 warm paper
  surface: "255 255 255", // #FFFFFF cards/panels
  "surface-alt": "247 242 234", // #F7F2EA sidebar/subtle fills
  foreground: "31 27 22", // #1F1B16 warm near-black
  "muted-fg": "140 130 117", // #8C8275
  "tertiary-fg": "168 159 144", // #A89F90 placeholder/tertiary
  border: "236 231 223", // #ECE7DF hairline
  "border-strong": "228 221 210", // #E4DDD2 input border
  primary: "13 148 136", // #0D9488 teal
  "primary-hover": "15 118 110", // #0F766E
  "primary-tint": "230 241 239", // #E6F1EF selection/active-nav bg
  "on-primary": "255 255 255",
  ok: "15 118 110", // #0F766E matched/identity
  "ok-bg": "230 241 239", // #E6F1EF
  success: "21 128 61", // #15803D
  "success-bg": "231 242 234", // #E7F2EA
  warn: "154 106 26", // #9A6A1A
  "warn-bg": "251 239 216", // #FBEFD8
  danger: "180 35 24", // #B42318
  "danger-bg": "253 236 234", // #FDECEA
  info: "31 111 173", // #1F6FAD
  "info-bg": "230 240 247", // #E6F0F7
} as const;

export type ColorName = keyof typeof colorTriplets;

/** Real CSS color string for a token, e.g. rgb("primary") -> "rgb(13 148 136)". */
export const rgb = (name: ColorName): string => `rgb(${colorTriplets[name]})`;

/** Warm-tinted shadow scale (brown-toned, not gray). */
export const shadows = {
  sm: "0 1px 2px rgba(70,55,30,.05)",
  md: "0 4px 12px -4px rgba(70,55,30,.12)",
  lg: "0 10px 30px -12px rgba(70,55,30,.20)",
  xl: "0 24px 60px -24px rgba(70,55,30,.35)",
} as const;

export const radii = { base: 10, panel: 12, pill: 20 } as const;

/** `:root{...}` declaration injected once in layout; Tailwind utilities read these. */
export const rootCssVars: string =
  ":root{" +
  Object.entries(colorTriplets)
    .map(([k, v]) => `--color-${k}: ${v};`)
    .join("") +
  "}";
