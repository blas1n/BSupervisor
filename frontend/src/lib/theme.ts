/**
 * BSVibe design token values for use in JS contexts (e.g. Recharts)
 * where CSS variables cannot be used directly.
 *
 * These values MUST match the @theme definitions in index.css.
 */
export const theme = {
  gray50: "#f2f3f7",
  gray100: "#e4e6ee",
  gray200: "#c8cbdb",
  gray300: "#a8adc6",
  gray400: "#8187a8",
  gray500: "#5a5f7d",
  gray600: "#3d4160",
  gray700: "#2a2d42",
  gray800: "#1e2033",
  gray850: "#181926",
  gray900: "#111218",
  gray950: "#0a0b0f",

  accent: "#f43f5e",
  accentLight: "#fb7185",
  accentDark: "#e11d48",

  success: "#10b981",
  successLight: "#34d399",

  warning: "#f59e0b",
  warningLight: "#fbbf24",
} as const;
