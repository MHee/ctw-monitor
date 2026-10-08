import { describe, it, expect } from 'vitest'
import { freshness } from './data.js'
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
