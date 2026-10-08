// onc-theme.js — ONC brand tokens + light/dark theme runtime for data apps.
// Framework-agnostic ES module (works in Vue/Vite, React, or plain <script type="module">).
// Colour values: ONC Brand Identity & Guidelines, March 2025 (pp. 12-15, Appendix 1).

export const ONC = {
  blue: '#129DC0', deepBlue: '#123253', black: '#000000', white: '#FFFFFF',
  red: '#B83726', orange: '#CE712F', yellow: '#FDB917', olive: '#7A8033',
  teal: '#4FAD99', midBlue: '#2E6BA1', purple: '#701261', grey: '#636466',
  tint:  { red:'#E78B88', orange:'#F2B26B', yellow:'#FFD17C', olive:'#B8C057',
           teal:'#91CDC1', blue:'#87BBE5', purple:'#C292BA', grey:'#B1B3B6' },
  shade: { red:'#731913', orange:'#763A19', yellow:'#9A6427', olive:'#3E461E',
           teal:'#183E37', blue:'#123253', purple:'#371B36', grey:'#414042' },
}

// Categorical series — same hue order in both themes
// (blue, orange, purple, olive, teal, red, yellow, grey), each >= 3:1 on its panel.
export const SERIES = {
  light: ['#2E6BA1', '#CE712F', '#701261', '#7A8033', '#183E37', '#B83726', '#9A6427', '#636466'],
  dark:  ['#87BBE5', '#F2B26B', '#C292BA', '#B8C057', '#91CDC1', '#E78B88', '#FFD17C', '#B1B3B6'],
}
// Emphasis colour for "the one line that matters" / hover overlays.
export const HIGHLIGHT = { light: '#129DC0', dark: '#129DC0' }

export const THEME_TOKENS = {
  light: { bg:'#F4F6F8', panel:'#FFFFFF', text:'#000000', muted:'#636466', grid:'#E1E3E6',
           axis:'#636466', border:'#B1B3B6', ok:'#183E37', warn:'#9A6427', error:'#B83726' },
  dark:  { bg:'#000000', panel:'#000000', text:'#FFFFFF', muted:'#B1B3B6', grid:'#2A2A2B',
           axis:'#B1B3B6', border:'#414042', ok:'#91CDC1', warn:'#FDB917', error:'#E78B88' },
}

export const FONTS = {
  display: "'Rajdhani', 'Segoe UI', system-ui, sans-serif",
  body: "'Open Sans', 'BC Sans', system-ui, sans-serif",
}

const STORAGE_KEY = 'onc-theme'
const listeners = new Set()
const mq = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null

/** 'light' | 'dark' — the theme currently in effect. */
export function currentTheme() {
  const forced = document.documentElement.getAttribute('data-theme')
  if (forced === 'light' || forced === 'dark') return forced
  return mq && mq.matches ? 'dark' : 'light'
}

/** Force 'light' | 'dark', or 'auto' to follow the OS. Persists to localStorage. */
export function setTheme(mode) {
  if (mode === 'auto') {
    document.documentElement.removeAttribute('data-theme')
    localStorage.removeItem(STORAGE_KEY)
  } else {
    document.documentElement.setAttribute('data-theme', mode)
    localStorage.setItem(STORAGE_KEY, mode)
  }
  emit()
}

export function toggleTheme() { setTheme(currentTheme() === 'dark' ? 'light' : 'dark') }

/** Subscribe to theme changes (explicit toggle or OS switch). Returns an unsubscribe fn. */
export function onThemeChange(cb) { listeners.add(cb); return () => listeners.delete(cb) }

function emit() { const t = currentTheme(); listeners.forEach((cb) => cb(t)) }
if (mq) mq.addEventListener('change', () => { if (!localStorage.getItem(STORAGE_KEY)) emit() })

/** Call once before mount (also inlined in index.html to avoid a flash). */
export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') document.documentElement.setAttribute('data-theme', saved)
}

export function tokens(theme = currentTheme()) { return THEME_TOKENS[theme] }
export function seriesColors(theme = currentTheme()) { return SERIES[theme] }

/**
 * Apply ONC defaults to Chart.js and keep every live chart in sync with the theme.
 *   import { Chart, registerables } from 'chart.js'
 *   Chart.register(...registerables); applyChartDefaults(Chart)
 * Components that hard-code dataset colours should read seriesColors() inside an
 * onThemeChange() callback and then call chart.update('none').
 */
export function applyChartDefaults(Chart) {
  const apply = (theme) => {
    const t = THEME_TOKENS[theme]
    Chart.defaults.color = t.axis
    Chart.defaults.borderColor = t.grid
    Chart.defaults.font.family = FONTS.body
    Chart.defaults.font.size = 12                     // >= 12px for axis ticks
    Chart.defaults.plugins.title.font = { family: FONTS.display, weight: '600', size: 15 }
    Chart.defaults.plugins.legend.labels.boxWidth = 12
    Chart.defaults.plugins.tooltip.backgroundColor = theme === 'dark' ? '#123253' : '#123253'
    Chart.defaults.plugins.tooltip.titleColor = '#FFFFFF'
    Chart.defaults.plugins.tooltip.bodyColor = '#FFFFFF'
    Chart.defaults.plugins.tooltip.cornerRadius = 0
    Chart.defaults.elements.line.borderWidth = 2
    Chart.defaults.elements.point.radius = 0
    Chart.defaults.elements.bar.backgroundColor = SERIES[theme][0]
    Chart.defaults.elements.line.borderColor = SERIES[theme][0]
    Object.values(Chart.instances || {}).forEach((c) => c.update('none'))
  }
  apply(currentTheme())
  onThemeChange(apply)
}

/** Colours for MapLibre layers over a GMRT/bathymetry basemap. */
export function mapColors(theme = currentTheme()) {
  return {
    backbone: ONC.blue,                  // NEPTUNE/VENUS backbone cable
    backboneCasing: theme === 'dark' ? '#000000' : '#FFFFFF',
    instrument: ONC.yellow,              // node / instrument markers
    instrumentStroke: ONC.deepBlue,
    selection: theme === 'dark' ? '#FFFFFF' : ONC.deepBlue,
    label: theme === 'dark' ? '#FFFFFF' : ONC.deepBlue,
    labelHalo: theme === 'dark' ? '#000000' : '#FFFFFF',
  }
}

/** Single-hue sequential ramp (white -> ONC Blue -> Deep Blue) for magnitude-only data. */
export const ONC_SEQUENTIAL = ['#FFFFFF', '#87BBE5', '#129DC0', '#2E6BA1', '#123253']
