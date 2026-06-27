import { describe, expect, it } from 'vitest'

import {
  createDefaultDesignInputs,
  mapDesignInputsToPlanningRequest,
  validateDesignInputs
} from './designInputs'

describe('design input model', () => {
  it('maps UI units to the backend planning contract', () => {
    const request = mapDesignInputsToPlanningRequest(createDefaultDesignInputs())

    expect(request).toMatchObject({
      daily_inbound_mass_kg: 25_000,
      working_time_h_per_day: 16,
      finished_storage_days: 2.5,
      packaging_storage_days: 3,
      main_packaging_storage_days: 3,
      auxiliary_packaging_storage_days: 30,
      utilization_factor: 0.85,
      reserve_factor: 1.05,
      raw_storage_ratio: 0.4,
      frozen_fruit_ratio: 0.1
    })
  })

  it('reports invalid positive values and ratios', () => {
    const inputs = createDefaultDesignInputs()
    inputs.dailyInboundMassTons = 0
    inputs.rawStorageRatio = 1.2

    expect(validateDesignInputs(inputs)).toEqual([
      { field: 'dailyInboundMassTons', message: '必须大于 0' },
      { field: 'rawStorageRatio', message: '必须在 0 到 1 之间' }
    ])
  })
})
