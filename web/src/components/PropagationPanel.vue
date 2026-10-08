<script setup>
// Distance-time (Hovmoller) diagram drawn on a plain canvas (about 1e5 cells).
// TODO(M1): axes with tick labels (time on x, along-coast km on y with gauge names),
// hatching for mask_km gaps, hover read-out, offset traces per gauge below the heatmap,
// and a screen-reader summary (latest anomaly at Neah Bay, latest event).
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { diverging, robustLimit } from '../lib/colormap.js'
import { onThemeChange } from '../lib/onc-theme.js'

const props = defineProps({
  grid: { type: Object, required: true },
  sealevel: { type: Object, default: null },
  stations: { type: Object, default: null },
})
const canvas = ref(null)
const vmax = ref(10)
let off = null

function draw() {
  const g = props.grid
  const nx = g.n, ny = g.distance_km.length
  const c = canvas.value
  c.width = nx; c.height = ny            // one pixel per cell; CSS scales it
  const ctx = c.getContext('2d')
  const img = ctx.createImageData(nx, ny)
  vmax.value = robustLimit(g.values)
  for (let t = 0; t < nx; t++) {
    for (let k = 0; k < ny; k++) {
      const rgb = diverging(g.values[t * ny + k], vmax.value)
      const row = ny - 1 - k                // poleward (larger km) at the top
      const p = 4 * (row * nx + t)
      if (rgb) { img.data[p] = rgb[0]; img.data[p + 1] = rgb[1]; img.data[p + 2] = rgb[2]; img.data[p + 3] = 255 }
      else { img.data[p + 3] = 0 }          // gap: panel background shows through
    }
  }
  ctx.putImageData(img, 0, 0)
}
onMounted(() => { draw(); off = onThemeChange(draw) })
onUnmounted(() => off?.())
watch(() => props.grid, draw)
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Along-coast propagation</h2>
    <div class="hov-box">
      <canvas ref="canvas" role="img"
              aria-label="Distance-time diagram of sea-level anomaly along the coast"></canvas>
    </div>
    <div class="colourbar">−{{ vmax }} cm <span>cmocean balance: blue low, red high</span> +{{ vmax }} cm</div>
    <p class="panel-note">{{ grid.processing }} · distance along the coast, 0 km at Neah Bay,
      poleward up · a poleward-propagating wave appears as a band sloping up to the right.</p>
  </section>
</template>
