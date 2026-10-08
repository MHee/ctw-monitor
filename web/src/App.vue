<script setup>
import { ref, computed, onMounted } from 'vue'
import OncHeader from './components/OncHeader.vue'
import OncFooter from './components/OncFooter.vue'
import DisclaimerBanner from './components/DisclaimerBanner.vue'
import StatusPanel from './components/StatusPanel.vue'
import PropagationPanel from './components/PropagationPanel.vue'
import LineChartPanel from './components/LineChartPanel.vue'
import EventsPanel from './components/EventsPanel.vue'
import ContextPanel from './components/ContextPanel.vue'
import MapPanel from './components/MapPanel.vue'
import { loadAll, eventMarkers, alignSeries, timeAxis, staleStations } from './lib/data.js'

const d = ref(null)
const error = ref('')
onMounted(async () => {
  try { d.value = await loadAll() } catch (e) { error.value = String(e.message || e) }
})
// ONC panels: shared time range, events passing NEPTUNE, Bamfield as the coastal reference
const RANGES = [{ id: '120', label: 'Last 120 days', days: 120 }, { id: 'all', label: 'Full window (400 days)', days: null }]
const range = ref('120')
const startMs = computed(() => {
  const r = RANGES.find((x) => x.id === range.value)
  const end = Date.parse(d.value?.manifest?.window?.end || '')
  return r?.days && Number.isFinite(end) ? end - r.days * 864e5 : null
})
const kmOf = computed(() => Object.fromEntries((d.value?.stations?.stations || [])
  .filter((s) => Number.isFinite(s.alongshore_km)).map((s) => [s.id, s.alongshore_km])))
function markersFor(product) {
  const kms = (product?.stations || []).map((id) => kmOf.value[id]).filter(Number.isFinite)
  if (!kms.length || !d.value?.events) return []
  return eventMarkers(d.value.events, kmOf.value, kms.reduce((a, b) => a + b, 0) / kms.length)
}
const bpMarkers = computed(() => markersFor(d.value?.bottom_pressure))
const tMarkers = computed(() => markersFor(d.value?.temperature))
const REF_GAUGE = 'bamfield'
const bpReference = computed(() => {
  const bp = d.value?.bottom_pressure, sl = d.value?.sealevel
  const v = bp && alignSeries(sl, REF_GAUGE, timeAxis(bp).map((t) => t.getTime()))
  return v ? { label: 'Bamfield sea level (tide gauge)', values: v } : null
})
const names = computed(() => Object.fromEntries((d.value?.stations?.stations || []).map((s) => [s.id, s.name])))
const stale = computed(() => d.value ? staleStations({ 'tide gauge': d.value.sealevel,
  'bottom pressure': d.value.bottom_pressure, temperature: d.value.temperature }, names.value) : [])
const MARKER_NOTE = 'Dashed vertical lines: best-propagating coastal events (see the propagation panel) at the time their fitted line passes these sites.'

const DATA_NOTE = 'Data: Ocean Networks Canada (Oceans 3.0), DFO-CHS, NOAA CO-OPS, IOC SLSMF, UHSLC, ECCC, Copernicus ERA5, NOAA CPC (ONI); basemap GMRT'
</script>

<template>
  <OncHeader title="Coastal-trapped wave monitor"
             subtitle="Subtidal sea level and bottom pressure, Central America to British Columbia" />
  <main class="app-main">
    <DisclaimerBanner :synthetic="d?.manifest?.synthetic" />
    <p v-if="error" class="banner">Data could not be loaded: {{ error }}</p>
    <template v-if="d">
      <div class="two-col">
        <StatusPanel :manifest="d.manifest" :stale="stale" />
        <ContextPanel v-if="d.context" :context="d.context" />
      </div>
      <PropagationPanel v-if="d.hovmoller" :grid="d.hovmoller" :sealevel="d.sealevel" :stations="d.stations" :events="d.events" />
      <MapPanel v-if="d.stations" :stations="d.stations" :sealevel="d.sealevel" />
      <fieldset class="event-mode range-switch">
        <legend>NEPTUNE panels</legend>
        <label v-for="r in RANGES" :key="r.id"><input :id="`range-${r.id}`" v-model="range" type="radio" :value="r.id"> {{ r.label }}</label>
      </fieldset>
      <div class="two-col">
        <LineChartPanel v-if="d.bottom_pressure" title="NEPTUNE bottom pressure, relative to Cascadia Basin"
                        :product="d.bottom_pressure" :stations="d.stations" y-label="Anomaly (cm of water)"
                        :start-ms="startMs" :markers="bpMarkers" :reference="bpReference"
                        :note="`Grey dashed: Bamfield sea level, IB-corrected, same cm scale (a bottom-pressure recorder already excludes the inverse-barometer response). ${MARKER_NOTE}`" />
        <LineChartPanel v-if="d.temperature" title="Slope temperature"
                        :product="d.temperature" :stations="d.stations" y-label="Anomaly (°C)"
                        :start-ms="startMs" :markers="tMarkers" :hidden="['fgppn_ctd']"
                        :note="`The shelf sensor FGPPN (25 m) is hidden by default: its seasonal and upwelling swings (about 1 °C) would hide the slope signal (about 0.1–0.3 °C). Click it in the legend to show it. ${MARKER_NOTE}`" />
      </div>
      <EventsPanel v-if="d.events" :events="d.events" :stations="d.stations" />
    </template>
  </main>
  <OncFooter :data-note="DATA_NOTE" repo-url="https://github.com/MHee/ctw-monitor" />
</template>
