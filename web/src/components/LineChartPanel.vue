<script setup>
// Generic line panel for a regular time-series product (docs/DATA_CONTRACT.md).
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Chart } from 'chart.js'
import { timeAxis } from '../lib/data.js'
import { seriesColors, onThemeChange } from '../lib/onc-theme.js'

const props = defineProps({
  title: { type: String, required: true },
  product: { type: Object, required: true },
  yLabel: { type: String, default: '' },
  stations: { type: Object, default: null },     // stations.json, for names and depths
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

function datasets() {
  const cols = seriesColors()
  return props.product.stations.map((id, i) => ({
    label: label(id),
    data: props.product.values[id],
    borderColor: cols[i % cols.length],
    borderDash: DASH[i % DASH.length],
    borderWidth: 1.5, pointRadius: 0, spanGaps: false,
  }))
}
function build() {
  chart?.destroy()
  chart = new Chart(el.value, {
    type: 'line',
    data: { labels: timeAxis(props.product), datasets: datasets() },
    options: {
      animation: false, maintainAspectRatio: false, parsing: true,
      interaction: { mode: 'index', intersect: false },
      scales: { x: { type: 'time' }, y: { title: { display: true, text: props.yLabel } } },
    },
  })
}
onMounted(() => {
  build()
  off = onThemeChange(() => {           // mutate in place (Chart.js metadata gotcha)
    const next = datasets()
    chart.data.datasets.forEach((ds, i) => { ds.borderColor = next[i].borderColor })
    chart.update('none')
  })
})
onUnmounted(() => { off?.(); chart?.destroy() })
watch(() => props.product, build)
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">{{ title }}</h2>
    <div class="chart-box"><canvas ref="el" :aria-label="title" role="img"></canvas></div>
    <p class="panel-note">{{ product.processing }}</p>
  </section>
</template>
