import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          500: "#2f5fdb",
          600: "#254bb3",
          700: "#1d3c8f",
        },
      },
    },
  },
  plugins: [],
};

export default config;
