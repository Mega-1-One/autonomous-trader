/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0d1117",
        surface: "#161b22",
        border: "#30363d",
        primary: "#2f81f7",
        success: "#238636",
        warning: "#d29922",
        danger: "#da3633",
        textPrimary: "#f0f6fc",
        textSecondary: "#8b949e",
      },
    },
  },
  plugins: [],
};
