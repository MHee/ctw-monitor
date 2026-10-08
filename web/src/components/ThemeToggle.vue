<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { currentTheme, toggleTheme, onThemeChange } from '../lib/onc-theme.js'
const theme = ref('light')
let off = null
onMounted(() => { theme.value = currentTheme(); off = onThemeChange((t) => { theme.value = t }) })
onUnmounted(() => off?.())
</script>

<template>
  <button class="secondary" type="button" @click="toggleTheme"
          :aria-label="`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`">
    {{ theme === 'dark' ? 'Light mode' : 'Dark mode' }}
  </button>
</template>
