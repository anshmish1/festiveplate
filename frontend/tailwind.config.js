/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        leaf: { 50: "#eef7ef", 100: "#d5ecd8", 200: "#acd8b3", 300: "#7dbf88", 400: "#4fa35f", 500: "#2f8443", 600: "#246a35", 700: "#1d542b", 800: "#174322", 900: "#10301a" },
        cream: { 50: "#fffdf7", 100: "#fdf8ec", 200: "#f8eed6", 300: "#f1e0b5" },
        turmeric: { 100: "#fdf0c8", 500: "#d99a06", 700: "#8a5f00" },
        chili: { 100: "#fde2df", 600: "#b42318", 700: "#8f1c13" },
      },
      fontFamily: { sans: ["Inter", "Noto Sans", "Noto Sans Kannada", "Noto Sans Devanagari", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
