<script setup>
// ONC app header: official logo + app title + theme toggle.
// Official logo copied from onc-brand-assets/logos. The Primary (blue box) logo is
// correct on the Deep Blue header; swap to the Reverse PNG if more contrast is needed.
import ThemeToggle from './ThemeToggle.vue'
defineProps({
  title: { type: String, required: true },       // sentence case, e.g. "DTS dashboard"
  subtitle: { type: String, default: '' },
  logoSrc: { type: String, default: new URL('../assets/ONC_Primary_screen_2024.png', import.meta.url).href },
})
</script>

<template>
  <header class="onc-app-header">
    <a href="https://www.oceannetworks.ca/" aria-label="Ocean Networks Canada home">
      <img class="onc-logo" :src="logoSrc" alt="Ocean Networks Canada" />
    </a>
    <div class="onc-app-title">
      <h1>{{ title }}</h1>
      <span v-if="subtitle" class="onc-app-subtitle">{{ subtitle }}</span>
    </div>
    <div class="onc-spacer"></div>
    <slot />
    <ThemeToggle />
  </header>
</template>
