<script setup>
// Context only (CLAUDE.md panel 6): the latest NOAA CPC ONI and RONI with links.
// Not a forecast for this coast, and the page is not an El Niño monitor (rule 1).
import { computed } from 'vue'

const props = defineProps({ context: { type: Object, required: true } })
const sign = (v) => (v > 0 ? '+' : '') + v.toFixed(1)   // NOAA publishes one decimal
const indices = computed(() => [
  { key: 'oni', name: 'ONI', link: 'NOAA CPC ONI table' },
  { key: 'roni', name: 'RONI', link: 'NOAA CPC RONI page' },
].filter((i) => props.context[i.key]).map((i) => ({ ...i, d: props.context[i.key] })))
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Context: Niño 3.4 indices</h2>
    <div class="oni-grid">
      <div v-for="i in indices" :key="i.key" class="oni-cell">
        <p class="oni-value">
          <span class="oni-name">{{ i.name }}</span>
          <span class="oni-number">{{ sign(i.d.anomaly_c) }} °C</span>
          <span>{{ i.d.season }} {{ i.d.year }}<template v-if="i.d.stale"> (not refreshed)</template></span>
        </p>
        <p v-if="i.d.recent?.length" class="panel-note num">
          <template v-for="(r, j) in i.d.recent.slice(-6)" :key="`${r.season}${r.year}`">{{ j ? ' · ' : '' }}{{ r.season }} {{ sign(r.anomaly_c) }}</template>
        </p>
        <p class="panel-note"><a :href="i.d.info_url || i.d.source_url" target="_blank" rel="noopener">{{ i.link }}</a></p>
      </div>
    </div>
    <p class="panel-note">
      3-month means of the sea-surface temperature anomaly in the Niño 3.4 region of the
      equatorial Pacific (ERSST v6), °C. ONI is the anomaly itself; RONI (Relative ONI) takes
      it relative to the tropical-mean anomaly and is NOAA's official ENSO index since 2026.
      Shown for context only; neither says anything by itself about sea level on this coast.
    </p>
  </section>
</template>
