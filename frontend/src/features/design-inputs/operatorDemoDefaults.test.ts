import { describe, expect, it } from 'vitest'

import { demoParameters } from './parameterCatalog'
import {
  OPERATOR_DEMO_MANIFEST_SOURCE,
  operatorDemoZoneNumeric,
  operatorDemoZoneValue
} from './operatorDemoDefaults'

describe('operator demo defaults', () => {
  it('reads v09 five KEY from the shared sample manifest', () => {
    expect(OPERATOR_DEMO_MANIFEST_SOURCE).toBe('samples/v09-process-input/manifest.json')
    expect(operatorDemoZoneValue('daily_inbound_mass_kg')).toBe('20000')
    expect(operatorDemoZoneNumeric('finished_storage_days')).toBe(7)
    expect(operatorDemoZoneNumeric('frozen_storage_days')).toBe(10)
    expect(operatorDemoZoneNumeric('main_packaging_storage_days')).toBe(4)
    expect(operatorDemoZoneNumeric('auxiliary_packaging_storage_days')).toBe(12)
  })

  it('does not keep a second 25000 / 2.5 demo set in the leftover catalog', () => {
    const byKey = Object.fromEntries(demoParameters.map((item) => [item.key, item.value]))
    expect(byKey.daily_inbound_mass_kg).toBe('20000')
    expect(byKey.finished_storage_days).toBe('7')
    expect(byKey.frozen_storage_days).toBe('10')
    expect(demoParameters.some((item) => item.value === '25000')).toBe(false)
    expect(demoParameters.some((item) => item.value === '2.5')).toBe(false)
  })
})
