<script setup>
// One sea-level anomaly trace per gauge, offset by a fixed spacing and ordered equatorward
// (bottom) to poleward (top), like the distance-time diagram above it.
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Chart } from 'chart.js'
import { timeAxis } from '../lib/data.js'
import { seriesColors, onThemeChange } from '../lib/onc-theme.js'

const props = defineProps({
  sealevel: { type: Object, required: true },
  stations: { type: Array, required: true },     // tide gauges sorted by alongshore_km
})
const SPACING_CM = 15
const el = ref(null)
let chart = null
let off = null

const rows = computed(() => props.stations.filter((s) => props.sealevel.values[s.id]))
const height = computed(() => `${Math.max(240, 22 * rows.value.length + 60)}px`)

function datasets() {
  const cols = seriesColors()
  return rows.value.map((s, i) => ({
    label: s.name,
    data: props.sealevel.values[s.id].map((v) => (v === null ? null : v + i * SPACING_CM)),
    offset: i * SPACING_CM,
    borderColor: cols[i % 2],                    // alternate two hues so neighbours separate
    borderWidth: 1.2, pointRadius: 0, spanGaps: false,
  }))
}

function build() {
  chart?.destroy()
  const names = rows.value.map((s) => s.name)
  chart = new Chart(el.value, {
    type: 'line',
    data: { labels: timeAxis(props.sealevel), datasets: datasets() },
    options: {
      animation: false, maintainAspectRatio: false,
      interaction: { mode: 'nearest', axis: 'xy', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `${c.dataset.label}: ${(c.parsed.y - c.dataset.offset).toFixed(1)} cm`,
          },
        },
      },
      scales: {
        x: { type: 'time' },
        y: {
          min: -SPACING_CM, max: rows.value.length * SPACING_CM,
          afterBuildTicks: (ax) => { ax.ticks = names.map((_, i) => ({ value: i * SPACING_CM })) },
          ticks: { autoSkip: false, callback: (v) => names[Math.round(v / SPACING_CM)] ?? '' },
          title: { display: true, text: `Anomaly, traces ${SPACING_CM} cm apart` },
        },
      },
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
watch(() => [props.sealevel, props.stations], build)
</script>

<template>
  <div class="traces-box" :style="{ height }">
    <canvas ref="el" role="img"
            aria-label="Sea-level anomaly at each tide gauge, offset traces ordered from Central America at the bottom to Prince Rupert at the top"></canvas>
  </div>
</template>
