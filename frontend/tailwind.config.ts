import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // Named tokens instead of raw hex scattered through components.
        brand: {
          50: "#eefdf5",
          100: "#d5f7e3",
          300: "#7fe6b3",
          500: "#12b76a", // primary — evokes travel/nature, not a generic SaaS blue
          600: "#0e9558",
          700: "#0b7a48",
          900: "#064026",
        },
        sunset: {
          50: "#fff1e9",
          400: "#ff9f68",
          500: "#ff7a3d", // accent for CTAs, itinerary highlights
          600: "#ec5c1a",
        },
        ink: {
          50: "#f7f8f8",
          100: "#eceef0",
          400: "#8a919b",
          700: "#33383f",
          900: "#15181c",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
      },
      boxShadow: {
        card: "0 4px 24px -4px rgba(21, 24, 28, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
