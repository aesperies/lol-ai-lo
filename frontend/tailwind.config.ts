import type { Config } from "tailwindcss";

/**
 * Lol-AI-lo design system — trustworthy, modern legal-tech.
 *
 * - brand: deep indigo (primary actions, links, focus)
 * - ink:   near-black navy (headings, brand surfaces)
 * - accent: warm gold (sparingly — the logo dot, premium highlights)
 * Typography: Fraunces (display/serif, legal character) + Inter (UI sans),
 * loaded via <link> in app/layout.tsx with system-font fallbacks.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Institutional navy — the primary brand colour (buttons, links, focus).
        brand: {
          50: "#eef1f6",
          100: "#d8e0ea",
          200: "#b3c2d6",
          300: "#7e95b4",
          400: "#4f6b92",
          500: "#2f4d74",
          600: "#1f3a5c",
          700: "#16233b",
          800: "#101a2c",
          900: "#0a1120",
        },
        // Cool navy-grey — text + neutral surfaces.
        ink: {
          50: "#f4f6f9",
          100: "#e6eaf0",
          200: "#cdd4e0",
          300: "#9aa3b5",
          400: "#5b6577",
          500: "#45506a",
          600: "#333c52",
          700: "#232c40",
          800: "#161d2d",
          900: "#0e1422",
        },
        // Restrained gold — sparingly (the logo dot, premium highlights).
        accent: {
          50: "#faf4e6",
          100: "#f0e3c0",
          200: "#e3cd92",
          400: "#c79a3a",
          500: "#b88a2a",
          600: "#946c1d",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "Cambria", "serif"],
        serif: ["var(--font-display)", "Georgia", "Cambria", "serif"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(14 17 28 / 0.04), 0 1px 3px 0 rgb(14 17 28 / 0.06)",
        elevated:
          "0 4px 12px -2px rgb(14 17 28 / 0.08), 0 2px 6px -2px rgb(14 17 28 / 0.06)",
        brand: "0 6px 16px -4px rgb(64 53 196 / 0.35)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.4s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
