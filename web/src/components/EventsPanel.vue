<script setup>
defineProps({ events: { type: Object, required: true } })
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Detected events</h2>
    <table class="events">
      <thead><tr><th>Event</th><th>Type</th><th>First seen</th><th>Speed (m/s)</th><th>95 % CI</th><th>r²</th><th>Gauges</th></tr></thead>
      <tbody>
        <tr v-for="e in events.events" :key="e.id">
          <td>{{ e.label || e.id }}</td><td>{{ e.type }}</td><td>{{ e.first?.slice(0, 10) }}</td>
          <td>{{ e.propagating ? e.speed_m_s?.toFixed(1) : 'not propagating' }}</td>
          <td>{{ e.speed_ci95 ? e.speed_ci95.map((v) => v.toFixed(1)).join('–') : '' }}</td>
          <td>{{ e.r2?.toFixed(2) }}</td><td>{{ e.n_stations }}</td>
        </tr>
      </tbody>
    </table>
    <p class="panel-note">Speed is fitted to the timing of extrema against along-coast distance,
      not from whole-window lag correlation.</p>
  </section>
</template>
