<script setup>
// CLAUDE.md rule 10. Keep this banner; edit wording with Martin.
defineProps({ synthetic: { type: Boolean, default: false } })
</script>

<template>
  <div class="banner prototype" role="note">
    <strong>Personal prototype.</strong> Built and maintained by Martin Heesemann to test the
    method. It is not an official Ocean Networks Canada data product, and its content and
    methods may change without notice.
  </div>
  <div v-if="synthetic" class="banner synthetic" role="alert">
    <strong>Sample data.</strong> Everything on this page is synthetic test data, not observations.
  </div>
  <div class="banner" role="note">
    This page shows observed subtidal sea-level and bottom-pressure anomalies. It is not a
    forecast. A coastal anomaly off British Columbia is not by itself evidence that an
    equatorial (El Niño) signal has arrived: local and regional winds drive much of it.
    IOC gauge data are real-time and not quality-controlled.
  </div>
</template>
