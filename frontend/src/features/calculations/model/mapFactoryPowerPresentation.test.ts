import { describe, expect, it } from 'vitest'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import type { FactoryPowerPresentation } from '../../../api/contracts/factoryPower'
import { mapFactoryPowerPresentation } from './mapFactoryPowerPresentation'

const VALID_CANONICAL_HASH = `sha256:${'a'.repeat(64)}`

const ATTACHED_PRESENTATION: FactoryPowerPresentation = {
  schema_version: '2.0.0-p1',
  source_calculator_id: 'factory_power_estimation',
  source_calculator_version: '2.0.0-p2',
  source_calculator_identity: 'factory_power_estimation@2.0.0-p2',
  canonical_result_hash: VALID_CANONICAL_HASH,
  factory_area_band: 'SMALL',
  unit_semantics: {
    power_unit: 'kW',
    energy_unit: 'kWh',
    not_energy: true,
    not_metered_electricity: true,
    not_daily_electricity_consumption: true
  },
  review: { requires_review: true, status: 'REQUIRES_ENGINEERING_REVIEW' },
  provenance: { rule_source: 'fixture' },
  assumptions: ['requires engineering review'],
  details: [{
    equipment_or_zone: 'public.electric_sliding_door',
    display_label: '冷库电动平移门',
    pool_label: '其他设备',
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
}

function canonicalRecord(overrides: Record<string, unknown> = {}): CalculationRunRecord {
  return {
    id: 'factory-power-1',
    project_id: 'project-1',
    project_version_id: 'version-1',
    calculator_name: 'factory_power_estimation',
    calculator_version: '2.0.0-p2',
    result_snapshot: {
      schema_version: '2.0.0-p1',
      result_kind: 'factory_power_canonical_result',
      success: true,
      calculator: {
        id: 'factory_power_estimation',
        version: '2.0.0-p2',
        identity: 'factory_power_estimation@2.0.0-p2'
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
    result_hash: `sha256:${'b'.repeat(64)}`,
    factory_power_presentation: ATTACHED_PRESENTATION,
    requires_review: true,
    ...overrides
  }
}

describe('mapFactoryPowerPresentation', () => {
  it('copies canonical values and selects the exact V2 calculator identity', () => {
    const presentation = mapFactoryPowerPresentation([canonicalRecord()])

    expect(presentation?.source_calculator_identity).toBe('factory_power_estimation@2.0.0-p2')
    expect(presentation?.canonical_result_hash).toBe(VALID_CANONICAL_HASH)
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

  it('fails closed when the attached presentation is null instead of reading raw canonical data', () => {
    const record = canonicalRecord({
      factory_power_presentation: null,
      result_hash: `sha256:${'c'.repeat(64)}`
    })
    const snapshot = record.result_snapshot as Record<string, unknown>
    const details = snapshot.details as Array<Record<string, unknown>>
    details[0].pool = 'POOL_X'

    expect(mapFactoryPowerPresentation([record])).toBeNull()
  })

  it('fails closed when the attached presentation is missing despite a valid-looking raw result', () => {
    const record = canonicalRecord({ result_hash: `sha256:${'d'.repeat(64)}` })
    delete record.factory_power_presentation

    expect(mapFactoryPowerPresentation([record])).toBeNull()
  })

  it('rejects an attached presentation with a non-hex SHA-256 hash', () => {
    const record = canonicalRecord({
      factory_power_presentation: {
        ...ATTACHED_PRESENTATION,
        canonical_result_hash: 'sha256:fixture-hash'
      }
    })

    expect(mapFactoryPowerPresentation([record])).toBeNull()
  })
})
