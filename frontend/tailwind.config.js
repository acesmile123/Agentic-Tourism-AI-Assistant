/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",   // toggle via document.documentElement.classList
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
    "./*.{js,jsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};