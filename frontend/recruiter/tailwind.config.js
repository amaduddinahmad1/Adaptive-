/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#0b1326',
          900: '#0f1730',
          850: '#141c30',
          800: '#171f33',
          750: '#1c2540',
          700: '#232c45',
          600: '#2a3450',
        },
        lavender: {
          100: '#ecebff',
          200: '#c0c1ff',
          300: '#b4b2ff',
          400: '#9b99ff',
          500: '#8b8dff',
          600: '#6f72e8',
        },
        ink: {
          DEFAULT: '#f8fafc',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        line: {
          DEFAULT: 'rgba(148, 163, 184, 0.14)',
          strong: 'rgba(192, 193, 255, 0.22)',
        },
        red: {
          DEFAULT: '#f87171',
          dim: 'rgba(248, 113, 113, 0.14)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        sm: '8px',
        md: '12px',
        lg: '16px',
        xl: '20px',
      },
      boxShadow: {
        panel: '0 18px 50px rgba(2, 6, 23, 0.35)',
      },
    },
  },
  plugins: [],
};
