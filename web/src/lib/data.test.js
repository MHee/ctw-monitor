import { describe, it, expect } from 'vitest'
import { freshness, eventRows, ageDays, eventLine, isBest, eventMarkers, alignSeries, firstIndex, staleStations, segmentSummary } from './data.js'
import { diverging, robustLimit, BALANCE } from './colormap.js'

describe('freshness', () => {
  const now = Date.parse('2026-10-07T00:00:00Z')
  it('is LIVE when recent', () => expect(freshness({ status: 'ok', last_observation: '2026-10-06T00:00:00Z' }, now)).toBe('LIVE'))
  it('is STALE after 3 days', () => expect(freshness({ status: 'ok', last_observation: '2026-10-02T00:00:00Z' }, now)).toBe('STALE'))
  it('is FAULT when failed', () => expect(freshness({ status: 'failed' }, now)).toBe('FAULT'))
})

describe('colormap', () => {
  it('maps zero to the centre colour', () => expect(diverging(0, 10)).toEqual(BALANCE[128]))
  it('has 256 entries', () => expect(BALANCE.length).toBe(256))
  it('returns null for gaps', () => expect(diverging(null, 10)).toBeNull())
  it('limits are symmetric and even', () => expect(robustLimit([1, -7, 3])).toBe(8))
})

describe('eventRows', () => {
  const now = Date.parse('2026-10-08T00:00:00Z')
  const ev = { events: [
    { id: 'a', first: '2026-05-17T18:00:00Z', major: true },
    { id: 'b', first: '2026-09-20T00:00:00Z', major: false },
    { id: 'c', first: '2026-01-01T00:00:00Z', major: false },
    { id: 'd', first: '2026-07-22T00:00:00Z', major: true },
  ] }
  it('puts major events first, newest first, then recent ones', () =>
    expect(eventRows(ev, now).rows.map((e) => e.id)).toEqual(['d', 'a', 'b']))
  it('counts what it leaves out', () => expect(eventRows(ev, now).hidden).toBe(1))
  it('copes with a missing product', () => expect(eventRows(null, now).rows).toEqual([]))
})

describe('ageDays', () => {
  it('floors to whole days', () => expect(ageDays('2026-10-06T12:00:00Z', Date.parse('2026-10-08T00:00:00Z'))).toBe(1))
  it('is null without a time', () => expect(ageDays(undefined)).toBeNull())
})

describe('eventLine', () => {
  const km = { a: 0, b: 259.2, c: 518.4 }               // 3 m/s = 259.2 km/day
  const ev = { extrema: [
    { station: 'a', time: '2026-05-17T00:00:00Z' },
    { station: 'b', time: '2026-05-18T00:00:00Z' },
    { station: 'c', time: '2026-05-19T00:00:00Z' },
  ] }
  it('recovers the speed as 1 / slowness', () => {
    const f = eventLine(ev, km)
    expect(1e6 / f.s).toBeCloseTo(3.0, 6)                 // s in ms/km -> m/s
    expect(f.kmMin).toBe(0); expect(f.kmMax).toBe(518.4)
  })
  it('needs two gauges with known distance', () => expect(eventLine({ extrema: [ev.extrema[0]] }, km)).toBeNull())
})

describe('isBest', () => {
  it('takes major propagating events', () => expect(isBest({ propagating: true, major: true, r2: 0.7, prominence_cm: 20 })).toBe(true))
  it('takes clean, sizeable ones', () => expect(isBest({ propagating: true, r2: 0.95, prominence_cm: 11 })).toBe(true))
  it('skips small ones', () => expect(isBest({ propagating: true, r2: 0.95, prominence_cm: 6 })).toBe(false))
  it('never takes non-propagating events', () => expect(isBest({ propagating: false, major: true, r2: 0.95, prominence_cm: 30 })).toBe(false))
})

describe('eventMarkers', () => {
  const km = { a: 0, b: 259.2, c: 518.4 }
  const ev = { events: [{ id: 'e', type: 'minimum', propagating: true, major: true, speed_m_s: 3, extrema: [
    { station: 'a', time: '2026-05-17T00:00:00Z' }, { station: 'b', time: '2026-05-18T00:00:00Z' },
    { station: 'c', time: '2026-05-19T00:00:00Z' }] }] }
  it('places the arrival on the fitted line', () =>
    expect(eventMarkers(ev, km, 259.2)[0].t).toBeCloseTo(Date.parse('2026-05-18T00:00:00Z'), -3))
  it('does not extrapolate far beyond the gauges', () => expect(eventMarkers(ev, km, 2000)).toEqual([]))
})

describe('alignSeries / firstIndex', () => {
  const p = { t0: '2026-01-01T00:00:00Z', dt_s: 21600, n: 4, values: { x: [1, 2, 3, 4] } }
  const T = (h) => Date.parse('2026-01-01T00:00:00Z') + h * 3600e3
  it('reads values at matching times', () => expect(alignSeries(p, 'x', [T(6), T(18), T(48)])).toEqual([2, 4, null]))
  it('finds the first index in a window', () => expect(firstIndex(p, T(7))).toBe(2))
})

describe('staleStations', () => {
  const now = Date.parse('2026-10-08T00:00:00Z')
  const bp = { stations: ['fgpd', 'ncbc'], meta: { fgpd: { last_valid: '2026-07-15T18:00:00Z' }, ncbc: { last_valid: '2026-10-07T00:00:00Z' } } }
  it('lists only stations without recent data', () =>
    expect(staleStations({ 'bottom pressure': bp }, { fgpd: 'FGPD' }, now).map((s) => s.name)).toEqual(['FGPD']))
  it('ignores products without last_valid', () => expect(staleStations({ t: { stations: ['a'], meta: {} } }, {}, now)).toEqual([]))
  it('flags an explicit null', () => expect(staleStations({ t: { stations: ['a'], meta: { a: { last_valid: null } } } }, {}, now)).toHaveLength(1))
})

describe('segmentSummary', () => {
  it('names propagating, southward and lag-free segments', () => expect(segmentSummary({ segments: [
    { name: 'California', speed_m_s: -24.5 },
    { name: 'Oregon and Washington', speed_m_s: 1.94, speed_ci95: [1.32, 3.65] },
    { name: 'British Columbia', speed_m_s: -3, speed_ci95: [-5, -2] },
  ] })).toBe('Calif. no clear lag · Ore.–Wash. 1.9 m/s · B.C. southward'))
})
