<script setup>
// Events table (docs/METHODS.md "Events and speed"). Non-propagating events stay in the
// table, greyed out, so storms that move the whole coast at once are visible as such.
import { computed } from 'vue'
import { eventRows, segmentSummary } from '../lib/data.js'

const props = defineProps({
  events: { type: Object, required: true },
  stations: { type: Object, default: null },
})
const names = computed(() => Object.fromEntries((props.stations?.stations || []).map((s) => [s.id, s.name])))
const name = (id) => names.value[id] || id
const table = computed(() => eventRows(props.events))
const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d).replace('-', '−') : '–')   // true minus sign
// an interval inverted from a slowness near zero can reach hundreds of m/s: say so plainly
const fmtCi = (v) => (Math.abs(v) > 50 ? (v > 0 ? '>50' : '<−50') : fmt(v))
function route(e) {
  const ex = e.extrema || []
  return ex.length ? `${name(ex[0].station)} → ${name(ex[ex.length - 1].station)}` : (e.label || e.id)
}
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Detected events</h2>
    <div class="table-scroll">
      <table class="events">
        <caption class="sr-only">Sea-level minima and maxima traced along the coast, with fitted speed</caption>
        <thead>
          <tr><th scope="col">First seen (UTC)</th><th scope="col">Type</th><th scope="col">Along the coast</th>
            <th scope="col">Gauges</th><th scope="col">Apparent along-coast speed (m/s) [95 % CI]</th><th scope="col">r²</th>
            <th scope="col">Size (cm)</th><th scope="col">Verdict</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in table.rows" :key="e.id" :class="{ 'not-prop': !e.propagating }">
            <td class="num">{{ e.first?.slice(0, 10) }} {{ e.first?.slice(11, 16) }}</td>
            <td>{{ e.type }}<span v-if="e.major" class="tag">major</span></td>
            <td>{{ route(e) }}<span v-if="e.segments?.length" class="sub">{{ segmentSummary(e) }}</span></td>
            <td class="num">{{ e.n_stations }} · {{ fmt(e.span_km, 0) }} km</td>
            <td class="num">{{ fmt(e.speed_m_s) }}<template v-if="e.speed_ci95"> [{{ fmtCi(e.speed_ci95[0]) }}, {{ fmtCi(e.speed_ci95[1]) }}]</template>
              <span v-if="'speed_loo' in e" class="sub">drop one gauge: {{ e.speed_loo ? `${fmtCi(e.speed_loo[0])} to ${fmtCi(e.speed_loo[1])}` : 'unbounded' }}</span></td>
            <td class="num">{{ fmt(e.r2, 2) }}</td>
            <td class="num">{{ fmt(e.prominence_cm) }}</td>
            <td><span class="verdict">{{ e.verdict || (e.propagating ? 'propagating' : 'not propagating') }}</span></td>
          </tr>
          <tr v-if="!table.rows.length"><td colspan="8">No events in the last 90 days.</td></tr>
        </tbody>
      </table>
    </div>
    <p class="panel-note">
      Major events (median size ≥ 15 cm) and all events of the last 90 days<template v-if="table.hidden">;
      {{ table.hidden }} older events not shown</template>. Size: median prominence of the extremum
      over its gauges, cm. Greyed rows do not propagate poleward at 1–10 m/s with r² ≥ 0.7.
    </p>
    <p class="panel-note">
      The speed is an apparent along-coast speed: coherent timing along the coast, which a
      wind-forced response can also produce, so it does not by itself show a free
      coastal-trapped wave. "Drop one gauge" is the range of speeds when each gauge in turn
      is left out; the 95 % interval assumes independent timing errors and is probably too
      narrow, because neighbouring gauges share weather. The line under each route repeats
      the fit per coast segment (split at Cape Mendocino and Cape Flattery): "no clear lag"
      means the extrema there are close to simultaneous.
    </p>
    <p class="panel-note">{{ events.processing || 'Speed is fitted to the timing of extrema against along-coast distance, not from whole-window lag correlation.' }}</p>
  </section>
</template>
