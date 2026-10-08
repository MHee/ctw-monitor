<script setup>
// Context only (CLAUDE.md panel 6): the latest NOAA CPC Oceanic Niño Index with a link.
// Not a forecast for this coast, and the page is not an El Niño monitor (rule 1).
import { computed } from 'vue'

const props = defineProps({ context: { type: Object, required: true } })
const oni = computed(() => props.context.oni)
const sign = (v) => (v > 0 ? '+' : '') + v.toFixed(1)   // NOAA publishes one decimal
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Context: Oceanic Niño Index</h2>
    <p class="oni-value">
      <span class="oni-number">{{ sign(oni.anomaly_c) }} °C</span>
      <span>{{ oni.season }} {{ oni.year }}</span>
    </p>
    <p v-if="oni.recent?.length" class="panel-note num">
      <template v-for="(r, i) in oni.recent.slice(-6)" :key="`${r.season}${r.year}`">{{ i ? ' · ' : '' }}{{ r.season }} {{ sign(r.anomaly_c) }}</template>
    </p>
    <p class="panel-note">
      NOAA CPC Oceanic Niño Index: 3-month mean sea-surface temperature anomaly in the Niño 3.4
      region of the equatorial Pacific (ERSST v6), °C. Shown for context only; it says nothing by itself
      about sea level on this coast.
      <a :href="oni.info_url || oni.source_url" target="_blank" rel="noopener">NOAA CPC ONI table</a>
    </p>
  </section>
</template>
