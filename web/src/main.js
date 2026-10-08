import { createApp } from 'vue'
import { Chart, registerables } from 'chart.js'
import 'chartjs-adapter-date-fns'
import './styles/onc-dashboard.css'          // imports ./onc-brand.css
import './styles/app.css'
import { initTheme, applyChartDefaults } from './lib/onc-theme.js'
import App from './App.vue'

initTheme()
Chart.register(...registerables)
applyChartDefaults(Chart)

createApp(App).mount('#app')
