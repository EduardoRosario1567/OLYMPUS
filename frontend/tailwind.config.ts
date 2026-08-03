import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      borderRadius: {
        xl: "0.85rem",
        "2xl": "1.15rem",
      },
    },
  },
  plugins: [],
};
export default config;
