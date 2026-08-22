import { describe, expect, it } from 'vitest'

import { resolveAgentAvailability } from '../../api/contracts/capabilities'

describe('resolveAgentAvailability', () => {
  it('returns available for LOCAL_TEST_AVAILABLE projection', () => {
    expect(
      resolveAgentAvailability([
        {
          name: 'model_backed_agent',
          status: 'available',
          capability_state: 'LOCAL_TEST_AVAILABLE'
        }
      ])
    ).toBe('available')
  })

  it('returns not_ready for enabled-not-ready projection', () => {
    expect(
      resolveAgentAvailability([
        {
          name: 'model_backed_agent',
          status: 'not_ready',
          capability_state: 'AGENT_CAPABILITY_ENABLED_NOT_READY'
        }
      ])
    ).toBe('not_ready')
  })

  it('returns unavailable when agent capability is missing', () => {
    expect(resolveAgentAvailability([])).toBe('unavailable')
  })
})
