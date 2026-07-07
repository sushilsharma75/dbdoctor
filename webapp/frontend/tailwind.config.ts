import type { Config } from 'tailwindcss';

// POSTMORTEM design tokens (see postmortem-reference.css): deep-blue ink
// backgrounds, warm bone text scale, severity flag accents, mono labels.
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          500: '#36507d',
          600: '#243657',
          700: '#182842',
          800: '#111d33',
          900: '#0b1424',
          950: '#070d1a',
        },
        bone: {
          50: '#fafaf9',
          100: '#f5f5f4',
          200: '#e7e5e4',
          300: '#d6d3d1',
          400: '#a8a29e',
          500: '#78716c',
          600: '#57534e',
        },
        flag: {
          critical: '#ef4444',
          warning: '#f59e0b',
          info: '#60a5fa',
          ok: '#10b981',
        },
      },
      fontFamily: {
        sans: ['Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      letterSpacing: {
        tightest: '-0.04em',
      },
    },
  },
  plugins: [],
};
export default config;
