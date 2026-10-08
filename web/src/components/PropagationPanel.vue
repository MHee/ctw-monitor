<script setup>
// Distance-time (Hovmoller) diagram on a plain canvas (about 1e5 cells). The grid is drawn at one
// pixel per cell offscreen and scaled up without smoothing; axes are drawn on the visible canvas.
// Cells without data (masked gaps, outages) are transparent and show the hatching underneath.
// TODO(M5): hover read-out, screen-reader summary (latest anomaly at Neah Bay, latest event).
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { diverging, robustLimit } from '../lib/colormap.js'
import { onThemeChange, tokens, FONTS } from '../lib/onc-theme.js'
import OffsetTraces from './OffsetTraces.vue'

const props = defineProps({
  grid: { type: Object, required: true },
  sealevel: { type: Object, default: null },
  stations: { type: Object, default: null },
})
const canvas = ref(null)
const box = ref(null)
const vmax = ref(10)
const M = { left: 118, right: 118, top: 8, bottom: 26 }  // plot margins, CSS px; labels both sides
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
let off = null
let ro = null
let lastSize = ''

// tide gauges in the product, equatorward to poleward
const gauges = computed(() => (props.stations?.stations || [])
  .filter((s) => s.kind === 'tide_gauge' && Number.isFinite(s.alongshore_km)
    && (!props.sealevel || props.sealevel.stations.includes(s.id)))
  .sort((a, b) => a.alongshore_km - b.alongshore_km))

function heatmap(g) {
  const nx = g.n, ny = g.distance_km.length
  const c = document.createElement('canvas')
  c.width = nx; c.height = ny
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(nx, ny)
  vmax.value = robustLimit(g.values)
  for (let t = 0; t < nx; t++) {
    for (let k = 0; k < ny; k++) {
      const rgb = diverging(g.values[t * ny + k], vmax.value)
      const p = 4 * ((ny - 1 - k) * nx + t)  // poleward (larger km) at the top
      if (rgb) { img.data[p] = rgb[0]; img.data[p + 1] = rgb[1]; img.data[p + 2] = rgb[2]; img.data[p + 3] = 255 }
    }
  }
  ctx.putImageData(img, 0, 0)
  return c
}

function draw() {
  const g = props.grid, c = canvas.value
  if (!c || !box.value?.clientWidth) return
  const dpr = window.devicePixelRatio || 1
  // size from the container, never from the canvas: its pixel size must not feed back into layout
  const W = box.value.clientWidth, H = c.clientHeight
  c.width = Math.round(W * dpr); c.height = Math.round(H * dpr)
  const ctx = c.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const tk = tokens()
  const pw = W - M.left - M.right, ph = H - M.top - M.bottom
  const km = g.distance_km
  const dk = km.length > 1 ? km[1] - km[0] : 50
  const lo = km[0] - dk / 2, hi = km[km.length - 1] + dk / 2
  const y = (d) => M.top + ph * (1 - (d - lo) / (hi - lo))
  const dt = g.dt_s * 1000, t0 = Date.parse(g.t0) - dt / 2, t1 = t0 + g.n * dt
  const x = (ms) => M.left + pw * (ms - t0) / (t1 - t0)

  // hatching (shows through cells without data), then the field
  ctx.save()
  ctx.beginPath(); ctx.rect(M.left, M.top, pw, ph); ctx.clip()
  ctx.strokeStyle = tk.border; ctx.lineWidth = 1
  for (let s = -ph; s < pw; s += 8) {
    ctx.beginPath(); ctx.moveTo(M.left + s, M.top + ph); ctx.lineTo(M.left + s + ph, M.top); ctx.stroke()
  }
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(heatmap(g), M.left, M.top, pw, ph)
  ctx.restore()
  ctx.strokeStyle = tk.axis; ctx.lineWidth = 1
  ctx.strokeRect(M.left + 0.5, M.top + 0.5, pw - 1, ph - 1)

  // y axis: gauge names at their along-coast distance, left column first; a name that would
  // overlap there goes to the right column; if both are taken, only the tick is drawn
  ctx.font = `12px ${FONTS.body}`
  ctx.fillStyle = tk.text; ctx.textBaseline = 'middle'
  const xr = M.left + pw
  let lastL = Infinity, lastR = Infinity
  for (const s of gauges.value) {
    const yy = y(s.alongshore_km)
    if (yy < M.top || yy > M.top + ph) continue
    ctx.beginPath(); ctx.moveTo(M.left - 4, yy); ctx.lineTo(M.left, yy); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(xr, yy); ctx.lineTo(xr + 4, yy); ctx.stroke()
    if (lastL - yy >= 13) {
      ctx.textAlign = 'right'; ctx.fillText(s.name, M.left - 6, yy); lastL = yy
    } else if (lastR - yy >= 13) {
      ctx.textAlign = 'left'; ctx.fillText(s.name, xr + 6, yy); lastR = yy
    }
  }

  // x axis: month ticks, labels thinned to at least ~48 px apart, year at January
  const d = new Date(t0); d.setUTCDate(1); d.setUTCHours(0, 0, 0, 0); d.setUTCMonth(d.getUTCMonth() + 1)
  const months = Math.max(1, (t1 - d.getTime()) / (30.44 * 864e5))
  const step = Math.max(1, Math.ceil(48 / (pw / months)))
  ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = tk.muted
  for (let i = 0; d.getTime() < t1; i++, d.setUTCMonth(d.getUTCMonth() + 1)) {
    const xx = x(d.getTime())
    ctx.beginPath(); ctx.moveTo(xx, M.top + ph); ctx.lineTo(xx, M.top + ph + 4); ctx.stroke()
    if (i % step === 0) {
      const m = d.getUTCMonth()
      ctx.fillText(m === 0 || i === 0 ? `${MONTHS[m]} ${d.getUTCFullYear()}` : MONTHS[m], xx, M.top + ph + 6)
    }
  }
}

onMounted(() => {
  draw()
  off = onThemeChange(draw)
  ro = new ResizeObserver(() => {
    const size = `${box.value.clientWidth}x${window.devicePixelRatio}`
    if (size !== lastSize) { lastSize = size; draw() }
  })
  ro.observe(box.value)
})
onUnmounted(() => { off?.(); ro?.disconnect() })
watch(() => [props.grid, props.stations], draw)
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Along-coast propagation</h2>
    <div ref="box" class="hov-box">
      <canvas ref="canvas" role="img"
              aria-label="Distance-time diagram of sea-level anomaly along the coast, Central America at the bottom, Prince Rupert at the top"></canvas>
    </div>
    <div class="colourbar">−{{ vmax }} cm <span>cmocean balance: blue low, red high; hatched: no data</span> +{{ vmax }} cm</div>
    <p class="panel-note">{{ grid.processing }} · distance along the coast, 0 km at Neah Bay,
      poleward up · a poleward-propagating wave appears as a band sloping up to the right.</p>
    <OffsetTraces v-if="sealevel" :sealevel="sealevel" :stations="gauges" />
  </section>
</template>
