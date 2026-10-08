import { describe, it, expect } from 'vitest'
import { freshness, eventRows, ageDays } from './data.js'
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
