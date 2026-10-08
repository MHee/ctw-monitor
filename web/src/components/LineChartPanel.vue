<script setup>
// Generic line panel for a regular time-series product (docs/DATA_CONTRACT.md).
// Optional: series hidden by default (one legend click shows them), a time window, an extra
// reference series on the same time axis, and vertical markers for coastal events.
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Chart } from 'chart.js'
import { timeAxis, firstIndex } from '../lib/data.js'
import { seriesColors, onThemeChange, tokens, FONTS } from '../lib/onc-theme.js'

const props = defineProps({
  title: { type: String, required: true },
  product: { type: Object, required: true },
  yLabel: { type: String, default: '' },
  stations: { type: Object, default: null },     // stations.json, for names and depths
  hidden: { type: Array, default: () => [] },    // station ids hidden until the legend is clicked
  startMs: { type: Number, default: null },      // show the product from this time on
  reference: { type: Object, default: null },    // { label, values } on this product's time axis
  markers: { type: Array, default: () => [] },   // [{ t (ms), label }]
  note: { type: String, default: '' },
})
const el = ref(null)
let chart = null
let off = null
const DASH = [[], [6, 3], [2, 2], [8, 3, 2, 3]]

function label(id) {
  const s = props.stations?.stations?.find((x) => x.id === id)
  if (!s) return id.replace(/_ctd$/, '').toUpperCase()
  return Number.isFinite(s.depth_m) ? `${s.name} ${s.depth_m} m` : s.name
}

function datasets(i0) {
  const cols = seriesColors()
  const out = props.product.stations.map((id, i) => ({
    label: label(id),
    data: props.product.values[id].slice(i0),
    hidden: props.hidden.includes(id),
    borderColor: cols[i % cols.length],
    borderDash: DASH[i % DASH.length],
    borderWidth: 1.5, pointRadius: 0, spanGaps: false,
  }))
  if (props.reference) {
    out.push({ label: props.reference.label, data: props.reference.values.slice(i0),
               borderColor: tokens().muted, borderDash: [3, 3], borderWidth: 1.25,
               pointRadius: 0, spanGaps: false, isReference: true })
  }
  return out
}

// Vertical event markers; each label goes to the first row where it does not overlap the
// previous label in that row.
const markerPlugin = {
  id: 'eventMarkers',
  afterDatasetsDraw(c) {
    const items = c.options.plugins.eventMarkers?.items || []
    const { ctx, chartArea: a, scales: { x } } = c
    const tk = tokens()
    ctx.save()
    ctx.font = `600 11px ${FONTS.body}`
    ctx.textBaseline = 'top'
    const shown = items.map((m) => ({ ...m, xx: x.getPixelForValue(m.t) }))
      .filter((m) => m.xx >= a.left && m.xx <= a.right)
    ctx.strokeStyle = tk.text; ctx.lineWidth = 1; ctx.setLineDash([4, 3])
    for (const m of shown) {               // all lines first, so no line crosses a label
      ctx.beginPath(); ctx.moveTo(m.xx, a.top); ctx.lineTo(m.xx, a.bottom); ctx.stroke()
    }
    ctx.setLineDash([])
    const rowEnd = []
    shown.forEach((m) => {
      const xx = m.xx
      const w = ctx.measureText(m.label).width
      const lx = Math.min(xx + 3, a.right - w - 2)
      let row = rowEnd.findIndex((end) => lx > end + 4)
      if (row < 0) row = rowEnd.length
      rowEnd[row] = lx + w
      const ly = a.top + 2 + row * 13
      ctx.fillStyle = tk.panel; ctx.fillRect(lx - 1, ly - 1, w + 2, 13)
      ctx.fillStyle = tk.text; ctx.fillText(m.label, lx, ly)
    })
    ctx.restore()
  },
}

function build() {
  chart?.destroy()
  const i0 = firstIndex(props.product, props.startMs)
  chart = new Chart(el.value, {
    type: 'line',
    data: { labels: timeAxis(props.product).slice(i0), datasets: datasets(i0) },
    options: {
      animation: false, maintainAspectRatio: false, parsing: true,
      interaction: { mode: 'index', intersect: false },
      scales: { x: { type: 'time' }, y: { title: { display: true, text: props.yLabel } } },
      plugins: { eventMarkers: { items: props.markers } },
    },
    plugins: [markerPlugin],
  })
}
onMounted(() => {
  build()
  off = onThemeChange(() => {           // mutate in place (Chart.js metadata gotcha)
    const next = datasets(0)
    chart.data.datasets.forEach((ds, i) => { ds.borderColor = next[i].borderColor })
    chart.update('none')
  })
})
onUnmounted(() => { off?.(); chart?.destroy() })
watch(() => [props.product, props.startMs, props.markers, props.reference], build)
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">{{ title }}</h2>
    <div class="chart-box"><canvas ref="el" :aria-label="title" role="img"></canvas></div>
    <p class="panel-note">{{ product.processing }}</p>
    <p v-if="note" class="panel-note">{{ note }}</p>
  </section>
</template>
