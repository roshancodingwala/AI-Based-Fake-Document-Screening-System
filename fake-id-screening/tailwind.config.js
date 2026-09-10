/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          DEFAULT: "rgb(var(--color-base) / <alpha-value>)",
          panel: "rgb(var(--color-base-panel) / <alpha-value>)",
          panel2: "rgb(var(--color-base-panel2) / <alpha-value>)",
          border: "rgb(var(--color-base-border) / <alpha-value>)",
          border2: "rgb(var(--color-base-border2) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--color-ink) / <alpha-value>)",
          muted: "rgb(var(--color-ink-muted) / <alpha-value>)",
          faint: "rgb(var(--color-ink-faint) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--color-accent) / <alpha-value>)",
          dim: "rgb(var(--color-accent-dim) / <alpha-value>)",
          bg: "rgb(var(--color-accent-bg) / <alpha-value>)",
        },
        danger:  { DEFAULT: "rgb(var(--color-danger)  / <alpha-value>)", bg: "rgb(var(--color-danger-bg)  / <alpha-value>)" },
        warning: { DEFAULT: "rgb(var(--color-warning) / <alpha-value>)", bg: "rgb(var(--color-warning-bg) / <alpha-value>)" },
        success: { DEFAULT: "rgb(var(--color-success) / <alpha-value>)", bg: "rgb(var(--color-success-bg) / <alpha-value>)" },
        info:    { DEFAULT: "rgb(var(--color-info)    / <alpha-value>)", bg: "rgb(var(--color-info-bg)    / <alpha-value>)" },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

