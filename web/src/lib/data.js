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
  const names = ['stations', 'sealevel', 'hovmoller', 'bottom_pressure', 'temperature', 'events', 'context']
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

// Events table rows (docs/METHODS.md item 7): major events first, then the rest of the
// last `days` days; newest first within each group. Non-propagating rows stay (greyed out).
export function eventRows(events, now = Date.now(), days = 90) {
  const recent = now - days * 86400000
  const list = (events?.events || []).map((e) => ({ ...e, t: Date.parse(e.first) }))
  const major = list.filter((e) => e.major).sort((a, b) => b.t - a.t)
  const rest = list.filter((e) => !e.major && e.t >= recent).sort((a, b) => b.t - a.t)
  return { rows: [...major, ...rest], hidden: list.length - major.length - rest.length }
}

// Age in whole days, for the status panel
export function ageDays(iso, now = Date.now()) {
  const t = Date.parse(iso || '')
  return Number.isFinite(t) ? Math.max(0, Math.floor((now - t) / 86400000)) : null
}

// Fitted line of an event in the distance-time plane, same orientation as the pipeline
// (time regressed on distance, docs/METHODS.md item 5): t(km) = a + s * km, in ms.
// kmOf: station id -> along-coast km. Returns null with fewer than two usable extrema.
export function eventLine(ev, kmOf) {
  const pts = (ev.extrema || [])
    .map((e) => ({ km: kmOf[e.station], t: Date.parse(e.time), station: e.station }))
    .filter((p) => Number.isFinite(p.km) && Number.isFinite(p.t))
  if (pts.length < 2) return null
  const mk = pts.reduce((a, p) => a + p.km, 0) / pts.length
  const mt = pts.reduce((a, p) => a + p.t, 0) / pts.length
  const sxx = pts.reduce((a, p) => a + (p.km - mk) ** 2, 0)
  if (sxx === 0) return null
  const s = pts.reduce((a, p) => a + (p.km - mk) * (p.t - mt), 0) / sxx
  const kms = pts.map((p) => p.km)
  return { a: mt - s * mk, s, kmMin: Math.min(...kms), kmMax: Math.max(...kms), pts }
}

// "Best propagators" highlighted on the plots: propagating and either major or clean and
// sizeable (r² >= 0.9, median size >= 10 cm). 9 of 34 propagating events in Oct 2026.
export const BEST = { r2: 0.9, prominence_cm: 10 }
export function isBest(e) {
  return !!e.propagating && (!!e.major || (e.r2 >= BEST.r2 && e.prominence_cm >= BEST.prominence_cm))
}

// Time at which each best-propagator event passes along-coast distance `km`, from its fitted
// line. Only events whose gauges span km (within tolKm) count: no extrapolation across gaps.
export function eventMarkers(events, kmOf, km, tolKm = 150) {
  const out = []
  for (const ev of events?.events || []) {
    if (!isBest(ev)) continue
    const f = eventLine(ev, kmOf)
    if (!f || km < f.kmMin - tolKm || km > f.kmMax + tolKm) continue
    out.push({ t: f.a + f.s * km, label: `${ev.type === 'minimum' ? 'min' : 'max'} ${ev.speed_m_s?.toFixed(1)} m/s`, id: ev.id })
  }
  return out.sort((a, b) => a.t - b.t)
}

// Values of station `id` in a regular product, read at the given times (ms); null where the
// product has no sample within half a step.
export function alignSeries(product, id, times) {
  const v = product?.values?.[id]
  if (!v) return null
  const t0 = Date.parse(product.t0), dt = product.dt_s * 1000
  return times.map((t) => {
    const i = Math.round((t - t0) / dt)
    return i >= 0 && i < v.length && Math.abs(t - (t0 + i * dt)) <= dt / 2 ? v[i] : null
  })
}

// First index of a regular product at or after `startMs` (0 if none given).
export function firstIndex(product, startMs) {
  if (!Number.isFinite(startMs)) return 0
  const t0 = Date.parse(product.t0), dt = product.dt_s * 1000
  return Math.min(product.n, Math.max(0, Math.ceil((startMs - t0) / dt)))
}

// Stations whose latest valid value (meta.last_valid) is older than `days`, across products.
export function staleStations(products, names = {}, now = Date.now(), days = 3) {
  const out = []
  for (const [label, p] of Object.entries(products)) {
    for (const id of p?.stations || []) {
      const last = p.meta?.[id]?.last_valid
      if (last === undefined) continue                 // product does not record it
      const age = ageDays(last, now)
      if (last === null || age === null || age > days) out.push({ id, name: names[id] || id, label, last, age })
    }
  }
  return out
}
