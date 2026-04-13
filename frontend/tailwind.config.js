/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        'bc-black':     'var(--bc-black)',
        'bc-surface':   'var(--bc-surface)',
        'bc-surface2':  'var(--bc-surface-2)',
        'bc-border':    'var(--bc-border)',
        'bc-text':      'var(--bc-text)',
        'bc-text-muted':'var(--bc-text-muted)',
        gold:           'var(--bc-gold)',
        'gold-hover':   'var(--bc-gold-hover)',
        'gold-light':   'var(--bc-gold-light)',
        'bc-success':   'var(--bc-success)',
        'bc-error':     'var(--bc-error)',
        'bc-warning':   'var(--bc-warning)',
      },
    },
  },
  plugins: [],
};
