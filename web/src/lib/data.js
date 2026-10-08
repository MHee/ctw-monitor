// Load products per docs/DATA_CONTRACT.md. Real data live in data/ (built by the pipeline,
// never committed). In dev, run `python -m ctw_monitor.cli synthetic --out web/public/data`.
const BASE = import.meta.env.BASE_URL
export const KNOWN_MAJOR = 0

async function getJSON(path) {
  const r = await fetch(`${BASE}data/${path}`, { cache: 'no-cache' })
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}

export async function loadAll() {
  const manifest = await getJSON('manifest.json')
  const major = Number(String(manifest.schema_version).split('.')[0])
  if (major !== KNOWN_MAJOR) throw new Error('data format changed')
  const names = ['stations', 'sealevel', 'hovmoller', 'bottom_pressure', 'temperature', 'events']
  const out = { manifest }
  await Promise.all(names.map(async (n) => {
    try { out[n] = await getJSON(`${n}.json`) } catch (e) { out[n] = null; console.warn(e) }
  }))
  return out
}

// Regular series -> Date array
export function timeAxis(p) {
  const t0 = Date.parse(p.t0)
  return Array.from({ length: p.n }, (_, i) => new Date(t0 + i * p.dt_s * 1000))
}

// Age of a source in days -> status word (CLAUDE.md: >3 d STALE, >14 d FAULT)
export function freshness(src, now = Date.now()) {
  if (src.status === 'failed') return 'FAULT'
  const last = Date.parse(src.last_observation || src.last_success || 0)
  const days = (now - last) / 86400000
  if (!isFinite(days) || days > 14) return 'FAULT'
  if (src.status === 'stale' || days > 3) return 'STALE'
  return 'LIVE'
}
