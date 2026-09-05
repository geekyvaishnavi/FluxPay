/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#17212b',
        mint: '#00a878',
        coral: '#e85d4f',
        gold: '#f2b84b',
      },
    },
  },
  plugins: [],
};
