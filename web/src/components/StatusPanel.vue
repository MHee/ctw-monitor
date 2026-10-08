<script setup>
import { computed } from 'vue'
import { freshness } from '../lib/data.js'
const props = defineProps({ manifest: { type: Object, required: true } })
const rows = computed(() => props.manifest.sources.map((s) => ({ ...s, word: freshness(s) })))
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">Data status</h2>
    <div class="status-bar">
      <span v-for="s in rows" :key="s.id" :class="['pill', s.word.toLowerCase() === 'live' ? 'ok' : s.word.toLowerCase()]"
            :title="s.message || ''">{{ s.id }} · {{ s.word }}</span>
    </div>
    <p class="panel-note">Built {{ manifest.generated_at }} · pipeline {{ manifest.pipeline.version }}
      ({{ manifest.pipeline.git_sha }})</p>
  </section>
</template>
