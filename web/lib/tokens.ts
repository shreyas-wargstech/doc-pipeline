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
  shadow: "60 45 25", // warm brown shadow base (light)
} as const;

export type ColorName = keyof typeof colorTriplets;

/** Option C "deep teal-tinted" dark palette. Same keys as colorTriplets. */
export const darkColorTriplets: Record<ColorName, string> = {
  background: "12 20 19",
  surface: "18 34 32",
  "surface-hover": "24 48 45",
  "surface-alt": "15 27 25",
  foreground: "220 239 233",
  "muted-fg": "127 163 154",
  "tertiary-fg": "92 125 117",
  border: "29 50 46",
  "border-strong": "42 70 63",
  primary: "20 184 166",
  "primary-hover": "45 212 191",
  "primary-tint": "17 48 43",
  secondary: "224 176 122",
  "secondary-hover": "236 197 150",
  "secondary-tint": "51 41 26",
  "on-primary": "4 20 15",
  "on-secondary": "26 20 8",
  ok: "45 212 191",
  "ok-bg": "17 48 43",
  success: "74 222 128",
  "success-bg": "17 39 26",
  warn: "251 191 36",
  "warn-bg": "46 36 16",
  danger: "248 113 113",
  "danger-bg": "46 22 22",
  info: "96 165 250",
  "info-bg": "21 35 58",
  shadow: "0 0 0", // pure-black shadow base (dark)
};

/** Real CSS color string for a token, e.g. rgb("primary") -> "rgb(13 148 136)". */
export const rgb = (name: ColorName): string => `rgb(${colorTriplets[name]})`;

/** Shadow scale; color comes from --color-shadow (warm in light, black in dark). */
export const shadows = {
  sm: "0 1px 2px rgb(var(--color-shadow) / 0.04)",
  md: "0 4px 12px -4px rgb(var(--color-shadow) / 0.10)",
  lg: "0 10px 30px -12px rgb(var(--color-shadow) / 0.16)",
  xl: "0 24px 60px -24px rgb(var(--color-shadow) / 0.28)",
} as const;

export const radii = { base: 8, panel: 12, pill: 24 } as const;

const block = (sel: string, triplets: Record<string, string>): string =>
  sel +
  "{" +
  Object.entries(triplets)
    .map(([k, v]) => `--color-${k}: ${v};`)
    .join("") +
  "}";

/**
 * Injected once in layout. `:root` holds light defaults; `.dark` overrides them.
 * `.dark` is a bare class (specificity 0,1,0) so `html.high-contrast` (0,1,1)
 * always wins. `color-scheme` keeps native controls/scrollbars in sync.
 */
export const themeCssVars: string =
  block(":root", colorTriplets) +
  block(".dark", darkColorTriplets) +
  ":root{color-scheme:light}.dark{color-scheme:dark}";
