# Branding (ONC 2025 visual identity)

Source: ONC Brand Identity & Guidelines, Staff Toolkit, March 2025, as encoded in the
`onc-brand` skill. Brand files (logos, fonts, guide PDF) are in
`OneDrive\Claude_Exchange\onc-brand-assets\`. Questions: onc-design@oceannetworks.ca.

Already in this repository:

| file | from |
|---|---|
| `web/src/styles/onc-brand.css` | design tokens, type scale, light and dark themes |
| `web/src/styles/onc-dashboard.css` | dashboard layer (`--bg --panel --text --accent --ok --warn --error`) |
| `web/src/lib/onc-theme.js` | `SERIES`, `HIGHLIGHT`, `applyChartDefaults`, `onThemeChange`, `mapColors` |
| `web/src/components/OncHeader.vue`, `OncFooter.vue`, `ThemeToggle.vue` | chrome |
| `web/src/assets/ONC_Primary_screen_2024.png`, `ONC_Primary_Reverse_screen_2024.png` | official logos |

## Rules

1. ONC Blue `#129DC0` is an accent: rules, focus rings, the highlighted trace. Never a
   large fill. On white it is 3.18:1, so no body text in ONC Blue; links use `#2E6BA1`.
2. Header and footer in Deep Blue `#123253` with a 3 px ONC Blue rule. Panels have
   square corners and an ONC Blue rule above the title.
3. Logo from the official files only, ≥ 55 px tall, with clear space; no recolouring,
   stretching or boxing. Never typeset "OCEAN NETWORKS CANADA".
4. Footer: "A University of Victoria initiative", the data-source line and a link to
   oceannetworks.ca. Credit every non-ONC source (see DATA_SOURCES.md).
5. Sentence case for titles ("Coastal-trapped wave monitor"). Uppercase only for
   NEPTUNE and VENUS.
6. Fonts: Rajdhani (display) and Open Sans (body), loaded from Google Fonts by
   `onc-brand.css`. To avoid sending visitor IPs to Google, self-host them from the brand
   folder (OFL licences included there) under `web/public/fonts/`. BC Sans for any
   Indigenous-language text.
7. Light and dark themes both ship; keep the pre-paint script in `index.html`.

## Colour for data

- Categorical series: `seriesColors()` from `onc-theme.js` (blue, orange, purple,
  olive, teal, red, yellow, grey; light and dark variants). Vary dash or marker too.
- The highlighted station or trace: `HIGHLIGHT` (ONC Blue).
- Anomaly heatmap: diverging, centred on zero, symmetric limits — cmocean *balance*
  (a scientific choice, not a brand one; the 256-entry table is in
  `web/src/lib/colormap.js`). Show the colour bar with units.
- Status pills: LIVE / STALE / FAULT with the word, never colour alone.
- Charts sit on the page or panel surface, not on Deep Blue.

## Accessibility

Body ≥ 15 px, axis ticks ≥ 12 px; every text/background pair ≥ 4.5:1; form controls
≥ 3:1 border; alt text on the logo and a text summary under each chart (latest value,
latest event) for screen readers.
