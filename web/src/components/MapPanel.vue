<script setup>
// Station map: GMRT relief, the coastal path that defines along-coast distance, tide gauges
// coloured by their latest anomaly (same colormap as the distance-time diagram), NEPTUNE sites.
import { ref, onMounted, onUnmounted, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { diverging, robustLimit } from '../lib/colormap.js'
import { onThemeChange, tokens, HIGHLIGHT, currentTheme } from '../lib/onc-theme.js'
import { timeAxis } from '../lib/data.js'

const props = defineProps({
  stations: { type: Object, required: true },
  sealevel: { type: Object, default: null },
})
const GMRT_WMS = 'https://www.gmrt.org/services/mapserver/wms_merc'
const GMRT_ATTR = 'GMRT v4.5, Global Multi-Resolution Topography (Ryan et al. 2009), <a href="https://www.gmrt.org">gmrt.org</a>'
const KM_TICK = 1000
const el = ref(null)
const vmax = ref(10)
let map = null
let layers = null
let off = null

// latest finite value per gauge and its time
function latest(id, times) {
  const v = props.sealevel?.values?.[id]
  if (!v) return null
  for (let i = v.length - 1; i >= 0; i--) {
    if (v[i] !== null) return { value: v[i], time: times[i] }
  }
  return null
}

// points every KM_TICK km along the path, linear in lat/lon between waypoints
function kmTicks(path) {
  const out = []
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1], b = path[i]
    for (let k = Math.ceil(a.alongshore_km / KM_TICK) * KM_TICK; k < b.alongshore_km; k += KM_TICK) {
      const f = (k - a.alongshore_km) / (b.alongshore_km - a.alongshore_km)
      out.push({ km: k, lat: a.lat + f * (b.lat - a.lat), lon: a.lon + f * (b.lon - a.lon) })
    }
  }
  return out
}

function rgb(c) { return c ? `rgb(${c[0]}, ${c[1]}, ${c[2]})` : null }

function draw() {
  layers?.clearLayers()
  const tk = tokens()
  const accent = HIGHLIGHT[currentTheme()]
  const path = props.stations.coastal_path || []
  if (path.length) {
    L.polyline(path.map((p) => [p.lat, p.lon]), { color: accent, weight: 2, opacity: 0.9 })
      .bindTooltip('Coastal path for along-coast distance', { sticky: true }).addTo(layers)
    for (const t of kmTicks(path)) {
      L.circleMarker([t.lat, t.lon], { radius: 2, color: accent, weight: 1, fillOpacity: 1 })
        .bindTooltip(`${t.km} km`, { permanent: true, direction: 'left', className: 'km-label' })
        .addTo(layers)
    }
  }
  const all = props.sealevel ? Object.values(props.sealevel.values).flat() : []
  vmax.value = robustLimit(all)
  const times = props.sealevel ? timeAxis(props.sealevel) : []
  for (const s of props.stations.stations) {
    if (s.kind === 'tide_gauge') {
      const last = latest(s.id, times)
      const meta = props.sealevel?.meta?.[s.id] || {}
      const fill = last ? rgb(diverging(last.value, vmax.value)) : tk.muted
      const tip = [`<strong>${s.name}</strong> (${s.provider})`,
        `${Math.round(s.alongshore_km)} km along the coast`,
        last ? `Latest anomaly ${last.value.toFixed(1)} cm, ${last.time.toISOString().slice(0, 13)}Z` : 'No recent data',
        meta.ib_source ? `IB: ${meta.ib_source}` : '',
        meta.stale ? 'Stale: last good values' : '',
        meta.not_qc ? 'Real-time, not quality-controlled' : ''].filter(Boolean).join('<br>')
      L.circleMarker([s.lat, s.lon], {
        radius: 7, color: tk.text, weight: 1.5, fillColor: fill, fillOpacity: 1,
        dashArray: last && !meta.stale ? null : '3 2',
      }).bindTooltip(tip).addTo(layers)
    } else {
      L.circleMarker([s.lat, s.lon], { radius: 4, color: accent, weight: 2, fillColor: tk.panel, fillOpacity: 1 })
        .bindTooltip(`<strong>${s.name}</strong> (ONC ${s.kind === 'ctd' ? 'CTD' : 'bottom pressure'}, ${s.depth_m} m)`)
        .addTo(layers)
    }
  }
}

onMounted(() => {
  map = L.map(el.value, { scrollWheelZoom: false, worldCopyJump: false })
  L.tileLayer.wms(GMRT_WMS, { layers: 'GMRT', format: 'image/png', version: '1.3.0', attribution: GMRT_ATTR })
    .addTo(map)
  layers = L.layerGroup().addTo(map)
  draw()
  const path = props.stations.coastal_path || []
  const pts = path.length ? path : props.stations.stations
  map.fitBounds(L.latLngBounds(pts.map((p) => [p.lat, p.lon])), { padding: [20, 20] })
  off = onThemeChange(draw)
})
onUnmounted(() => { off?.(); map?.remove() })
watch(() => [props.stations, props.sealevel], draw)
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Stations and coastal path</h2>
    <div ref="el" class="map-box" role="region"
         aria-label="Map of tide gauges and NEPTUNE sites along the coastal path from El Salvador to Prince Rupert"></div>
    <p class="panel-note">Tide gauges (circles) coloured by their latest anomaly on the same scale as the
      distance-time diagram (±{{ vmax }} cm); dashed outline: stale or no recent data. Small rings: NEPTUNE
      bottom-pressure and CTD sites. Blue line: the path along which distance is measured, labelled every
      {{ KM_TICK }} km (0 km at Neah Bay). Basemap: GMRT.</p>
  </section>
</template>
