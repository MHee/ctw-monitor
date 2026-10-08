<script setup>
// Relationship statement is required on all ONC communications (brand guide p. 7).
defineProps({
  repoUrl: { type: String, default: '' },
  dataNote: { type: String, default: 'Data: Ocean Networks Canada Oceans 3.0 (data.oceannetworks.ca)' },
})
</script>

<template>
  <footer class="onc-app-footer">
    <span class="onc-uvic">A University of Victoria initiative</span>
    <span>{{ dataNote }}</span>
    <a href="https://www.oceannetworks.ca/">oceannetworks.ca</a>
    <a v-if="repoUrl" :href="repoUrl">Source code</a>
  </footer>
</template>
