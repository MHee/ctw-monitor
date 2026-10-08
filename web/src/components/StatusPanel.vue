<script setup>
// Data status (CLAUDE.md panel 5): LIVE / STALE / FAULT per source from manifest.json.
import { computed } from 'vue'
import { freshness, ageDays } from '../lib/data.js'

const props = defineProps({ manifest: { type: Object, required: true } })
const NAMES = {
  noaa_coops: 'NOAA CO-OPS tide gauges', chs_iwls: 'CHS tide gauges', ioc_slsmf: 'IOC tide gauges',
  uhslc_fast: 'UHSLC tide gauges', onc_bpr: 'ONC bottom pressure', onc_ctd: 'ONC CTD temperature',
  noaa_oni: 'NOAA ONI (context)',
}
const rows = computed(() => props.manifest.sources.map((s) => {
  const word = freshness(s)
  return { ...s, word, cls: word === 'LIVE' ? 'ok' : word.toLowerCase(), name: NAMES[s.id] || s.id,
           age: ageDays(s.last_observation || s.last_success) }
}))
const problems = computed(() => rows.value.filter((r) => r.word !== 'LIVE' || r.message).length)
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Data status</h2>
    <div class="status-bar">
      <span v-for="s in rows" :key="s.id" :class="['pill', s.cls]">{{ s.name }} · {{ s.word }}</span>
    </div>
    <details class="status-details">
      <summary>Details{{ problems ? ` (${problems} with notes)` : '' }}</summary>
      <div class="table-scroll">
        <table class="events">
          <thead><tr><th scope="col">Source</th><th scope="col">State</th><th scope="col">Latest data (UTC)</th>
            <th scope="col">Age (days)</th><th scope="col">Note</th></tr></thead>
          <tbody>
            <tr v-for="s in rows" :key="s.id">
              <td>{{ s.name }}</td><td>{{ s.word }}</td>
              <td class="num">{{ (s.last_observation || s.last_success || '–').slice(0, 16).replace('T', ' ') }}</td>
              <td class="num">{{ s.age ?? '–' }}</td><td>{{ s.message || '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
    <p class="panel-note">LIVE: data within 3 days; STALE: older, or last good product reused after a
      failed fetch; FAULT: failed or older than 14 days. Built {{ manifest.generated_at }} · pipeline
      {{ manifest.pipeline.version }} ({{ manifest.pipeline.git_sha }})</p>
  </section>
</template>
