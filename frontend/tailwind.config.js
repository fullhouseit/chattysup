/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        primary: {
          DEFAULT: "#1F93FF",
          50: "#EFF7FF",
          100: "#DBEDFF",
          200: "#BEDFFF",
          300: "#91CBFF",
          400: "#5DAEFF",
          500: "#1F93FF",
          600: "#0F76E0",
          700: "#0D5DB4",
          800: "#114F94",
          900: "#14447A",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          muted: "#F9FAFB",
        },
        line: "#E5E7EB",
        note: "#FEF3C7",
        ink: {
          DEFAULT: "#111827",
          soft: "#374151",
          muted: "#6B7280",
          faint: "#9CA3AF",
        },
      },
      fontSize: {
        "2xs": ["11px", "16px"],
        xs: ["12px", "17px"],
        sm: ["13px", "19px"],
        base: ["14px", "21px"],
        md: ["15px", "23px"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16, 24, 40, 0.05)",
        pop: "0 10px 30px -8px rgba(16, 24, 40, 0.18), 0 2px 6px rgba(16,24,40,0.06)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "translateY(4px) scale(0.98)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        blink: {
          "0%, 100%": { opacity: "0.25" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 120ms ease-out",
        "scale-in": "scale-in 120ms ease-out",
        blink: "blink 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
