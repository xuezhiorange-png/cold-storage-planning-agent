import { describe, expect, it } from 'vitest'

import { LatestRequestGate } from './latestRequestGate'

describe('LatestRequestGate', () => {
  it('aborts the previous request when a newer request starts', () => {
    const gate = new LatestRequestGate()
    const first = gate.begin()
    const second = gate.begin()

    expect(first.signal.aborted).toBe(true)
    expect(first.isCurrent()).toBe(false)
    expect(second.signal.aborted).toBe(false)
    expect(second.isCurrent()).toBe(true)
  })

  it('keeps completion of an old request from clearing the active request', () => {
    const gate = new LatestRequestGate()
    const first = gate.begin()
    const second = gate.begin()

    first.finish()

    expect(second.isCurrent()).toBe(true)
    expect(second.signal.aborted).toBe(false)
  })

  it('cancels the active request explicitly', () => {
    const gate = new LatestRequestGate()
    const request = gate.begin()

    gate.cancel()

    expect(request.signal.aborted).toBe(true)
    expect(request.isCurrent()).toBe(false)
  })
})
