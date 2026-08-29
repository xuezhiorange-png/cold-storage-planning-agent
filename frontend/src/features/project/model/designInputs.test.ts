import { describe, expect, it } from 'vitest'

import {
  createDefaultDesignInputs,
  DEMO_MIGRATION_GAP_COEFFICIENTS,
  mapDesignInputsToPlanningRequest
} from './designInputs'

describe('design input model', () => {
  it('maps persisted coefficient fields from form state, not silent defaults', () => {
    const inputs = createDefaultDesignInputs()
    inputs.utilizationFactor = 0.72
    inputs.reserveFactor = 1.08
    const request = mapDesignInputsToPlanningRequest(inputs)

    expect(request.utilization_factor).toBe(0.72)
    expect(request.reserve_factor).toBe(1.08)
  })

  it('exposes demo migration gap defaults explicitly in form defaults', () => {
    const defaults = createDefaultDesignInputs()
    expect(defaults.utilizationFactor).toBe(DEMO_MIGRATION_GAP_COEFFICIENTS.utilization_factor)
    expect(defaults.reserveFactor).toBe(DEMO_MIGRATION_GAP_COEFFICIENTS.reserve_factor)
  })

  it('maps UI units to the backend planning contract', () => {
    const request = mapDesignInputsToPlanningRequest(createDefaultDesignInputs())

    expect(request).toMatchObject({
      daily_inbound_mass_kg: 20_000,
      working_time_h_per_day: 16,
      finished_storage_days: 7,
      packaging_storage_days: 4,
      main_packaging_storage_days: 4,
      auxiliary_packaging_storage_days: 12,
      utilization_factor: 0.85,
      reserve_factor: 1.05,
      raw_storage_ratio: 0.4,
      frozen_fruit_ratio: 0.1,
      frozen_storage_days: 10
    })
  })
})
