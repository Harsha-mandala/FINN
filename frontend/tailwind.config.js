/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // FINN brand — dark navy + electric blue accent
        surface: {
          DEFAULT: '#0F172A',  // deep navy background
          card: '#1E293B',     // card surface
          elevated: '#263548', // elevated card
        },
        accent: {
          DEFAULT: '#3B82F6',  // electric blue
          dim: '#1D4ED8',
          muted: '#1E3A5F',
        },
        success: '#22C55E',
        danger: '#EF4444',
        warning: '#F59E0B',
        muted: '#64748B',
        subtle: '#94A3B8',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        card: '12px',
      },
    },
  },
  plugins: [],
}
