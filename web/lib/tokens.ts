/** Single source of truth for design tokens. */

/** name -> "R G B" (space-separated, no rgb() wrapper) */
export const colorTriplets = {
  background: "249 247 244", // warm cream
  surface: "255 255 255",
  "surface-hover": "245 242 237",
  "surface-alt": "237 232 224",
  foreground: "26 23 20",
  "muted-fg": "122 114 104",
  "tertiary-fg": "168 160 148",
  border: "228 223 215",
  "border-strong": "216 210 200",
  primary: "13 148 136", // teal
  "primary-hover": "15 118 110",
  "primary-tint": "232 244 242",
  secondary: "196 154 108", // amber
  "secondary-hover": "176 133 79",
  "secondary-tint": "245 237 227",
  "on-primary": "255 255 255",
  "on-secondary": "255 255 255",
  ok: "15 118 110",
  "ok-bg": "232 244 242",
  success: "21 128 61",
  "success-bg": "231 242 234",
  warn: "180 83 9",
  "warn-bg": "254 243 199",
  danger: "185 28 28",
  "danger-bg": "253 236 236",
  info: "37 99 235",
  "info-bg": "239 246 255",
} as const;

export type ColorName = keyof typeof colorTriplets;

/** Real CSS color string for a token, e.g. rgb("primary") -> "rgb(13 148 136)". */
export const rgb = (name: ColorName): string => `rgb(${colorTriplets[name]})`;

/** Warm-tinted shadow scale (brown-toned, not gray). */
export const shadows = {
  sm: "0 1px 2px rgba(60,45,25,0.04)",
  md: "0 4px 12px -4px rgba(60,45,25,0.10)",
  lg: "0 10px 30px -12px rgba(60,45,25,0.16)",
  xl: "0 24px 60px -24px rgba(60,45,25,0.28)",
} as const;

export const radii = { base: 8, panel: 12, pill: 24 } as const;

/** `:root{...}` declaration injected once in layout; Tailwind utilities read these. */
export const rootCssVars: string =
  ":root{" +
  Object.entries(colorTriplets)
    .map(([k, v]) => `--color-${k}: ${v};`)
    .join("") +
  "}";
