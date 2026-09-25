/**
 * Chart colors mirroring the CSS tokens in app/globals.css. SVG attributes
 * passed through Recharts cannot read Tailwind classes, so charts use these.
 */
export const palette = {
  ink: "#171512",
  muted: "#48443E",
  faint: "#5C574F",
  rule: "#B5B3AE",
  paper: "#D1D0CC",
  surface: "#DAD9D5",
  accent: "#A02E17",
  cool: "#2E628C",
  neutral: "#76716A",
  empty: "#A9A7A1",
  caution: "#6B4D0F",
  confirm: "#245A42",
} as const;
