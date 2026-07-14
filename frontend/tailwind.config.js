/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f7f8fa",
        card: "#ffffff",
        ink: "#0f172a",
        subtle: "#64748b",
      },
      boxShadow: {
        soft: "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
        lift: "0 4px 20px rgba(15,23,42,0.08)",
      },
    },
  },
  plugins: [],
};
