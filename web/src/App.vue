<script setup>
import { ref, onMounted } from 'vue'
import OncHeader from './components/OncHeader.vue'
import OncFooter from './components/OncFooter.vue'
import DisclaimerBanner from './components/DisclaimerBanner.vue'
import StatusPanel from './components/StatusPanel.vue'
import PropagationPanel from './components/PropagationPanel.vue'
import LineChartPanel from './components/LineChartPanel.vue'
import EventsPanel from './components/EventsPanel.vue'
import ContextPanel from './components/ContextPanel.vue'
import MapPanel from './components/MapPanel.vue'
import { loadAll } from './lib/data.js'

const d = ref(null)
const error = ref('')
onMounted(async () => {
  try { d.value = await loadAll() } catch (e) { error.value = String(e.message || e) }
})
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
        <StatusPanel :manifest="d.manifest" />
        <ContextPanel v-if="d.context" :context="d.context" />
      </div>
      <PropagationPanel v-if="d.hovmoller" :grid="d.hovmoller" :sealevel="d.sealevel" :stations="d.stations" />
      <MapPanel v-if="d.stations" :stations="d.stations" :sealevel="d.sealevel" />
      <div class="two-col">
        <LineChartPanel v-if="d.bottom_pressure" title="NEPTUNE cross-margin bottom pressure"
                        :product="d.bottom_pressure" :stations="d.stations" y-label="Anomaly (cm of water)" />
        <LineChartPanel v-if="d.temperature" title="Slope temperature"
                        :product="d.temperature" :stations="d.stations" y-label="Anomaly (°C)" />
      </div>
      <EventsPanel v-if="d.events" :events="d.events" :stations="d.stations" />
    </template>
  </main>
  <OncFooter :data-note="DATA_NOTE" repo-url="https://github.com/MHee/ctw-monitor" />
</template>
