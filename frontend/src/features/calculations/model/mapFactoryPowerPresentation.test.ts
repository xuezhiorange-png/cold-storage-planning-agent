import { describe, expect, it } from 'vitest'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import { mapFactoryPowerPresentation } from './mapFactoryPowerPresentation'

function canonicalRecord(overrides: Record<string, unknown> = {}): CalculationRunRecord {
  return {
    id: 'factory-power-1',
    project_id: 'project-1',
    project_version_id: 'version-1',
    calculator_name: 'factory_power_estimation',
    calculator_version: '2.0.0-p1',
    result_snapshot: {
      schema_version: '2.0.0-p1',
      result_kind: 'factory_power_canonical_result',
      success: true,
      calculator: {
        id: 'factory_power_estimation',
        version: '2.0.0-p1',
        identity: 'factory_power_estimation@2.0.0-p1'
      },
      input_authority: { factory_area_m2: '2500' },
      factory_area_band: 'SMALL',
      unit_semantics: {
        power_unit: 'kW',
        energy_unit: 'kWh',
        not_energy: true,
        not_metered_electricity: true,
        not_daily_electricity_consumption: true
      },
      provenance: { rule_source: 'fixture' },
      assumptions: ['requires engineering review'],
      review: { requires_review: true, status: 'REQUIRES_ENGINEERING_REVIEW' },
      details: [{
        equipment_or_zone: 'public.electric_sliding_door',
        basis: 'factory_area_band',
        configured_quantity: 7,
        unit_power_kw: '0.5',
        installed_power_kw: '3.5',
        pool: 'POOL_B',
        simultaneity_factor: '0.8',
        coincident_power_kw: '123.456'
      }],
      summary: {
        defrost_installed_power_kw: '1',
        defrost_coincident_power_kw: '0.3',
        other_installed_power_kw: '3.5',
        other_coincident_power_kw: '123.456',
        production_equipment_installed_power_kw: '200',
        production_equipment_coincident_power_kw: '170',
        total_installed_power_kw: '204.5',
        estimated_total_power_kw: '999.999'
      }
    },
    result_hash: 'sha256:fixture-hash',
    requires_review: true,
    ...overrides
  }
}

describe('mapFactoryPowerPresentation', () => {
  it('copies canonical values and selects the exact V2 calculator identity', () => {
    const presentation = mapFactoryPowerPresentation([canonicalRecord()])

    expect(presentation?.source_calculator_identity).toBe('factory_power_estimation@2.0.0-p1')
    expect(presentation?.canonical_result_hash).toBe('sha256:fixture-hash')
    expect(presentation?.summary.estimated_total_power_kw).toBe('999.999')
    expect(presentation?.details[0].configured_quantity).toBe(7)
    expect(presentation?.details[0].simultaneity_factor).toBe('0.8')
    expect(presentation?.details[0].coincident_power_kw).toBe('123.456')
    expect(presentation?.details[0].display_label).toBe('冷库电动平移门')
  })

  it('returns no V2 result instead of falling back to legacy power records', () => {
    const records = [
      canonicalRecord({
        id: 'legacy-installed',
        calculator_name: 'installed_power',
        calculator_version: '1.0.0',
        result_hash: 'hash-installed'
      }),
      canonicalRecord({
        id: 'legacy-supplemental',
        calculator_name: 'power_configuration',
        calculator_version: '1.0.0',
        result_hash: 'hash-supplemental'
      })
    ]

    expect(mapFactoryPowerPresentation(records)).toBeNull()
  })

  it('fails closed when a V2 result has no source hash or required summary field', () => {
    const record = canonicalRecord({ result_hash: undefined })
    const snapshot = record.result_snapshot as Record<string, unknown>
    const summary = snapshot.summary as Record<string, unknown>
    delete summary.estimated_total_power_kw

    expect(mapFactoryPowerPresentation([record])).toBeNull()
  })
})
