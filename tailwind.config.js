/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./app/templates/**/*.html'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
      borderRadius: { sm: '3px', DEFAULT: '3px', md: '4px', lg: '6px' },
    },
  },
  plugins: [],
};
