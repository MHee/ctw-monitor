import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// VITE_BASE is set by the Pages workflow to '/<repo>/'.
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [vue()],
  // On Windows, 'localhost' can bind to IPv6 ::1 only; pin IPv4 for Tailscale/phone testing.
  server: { host: '127.0.0.1', port: 5173 },
  test: { environment: 'node' },
})
