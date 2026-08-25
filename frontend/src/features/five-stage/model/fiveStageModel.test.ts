import { describe, expect, it } from 'vitest'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import {
  buildEngineeringInputBundle,
  createDefaultEngineeringInputFormState,
  fieldPathToFormKey
} from './engineeringInputForm'
import { mapFiveStageProgress } from './mapFiveStageCalculations'

function fiveStageRecord(
  calculatorName: string,
  overrides: Partial<CalculationRunRecord> = {}
): CalculationRunRecord {
  return {
    id: `calc-${calculatorName}`,
    calculation_id: `calc-${calculatorName}`,
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: calculatorName,
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: calculatorName,
      calculator_version: '1.0.0',
      input: {},
      result: {}
    },
    result_hash: `hash-${calculatorName}`,
    requires_review: true,
    ...overrides
  }
}

describe('engineeringInputForm', () => {
  it('builds bundle with all KEY leaves and condensing_temperature_c', () => {
    const form = createDefaultEngineeringInputFormState()
    const bundle = buildEngineeringInputBundle(form, {
      projectId: 'proj-1',
      projectVersionId: 'ver-1',
      versionNumber: 1,
      versionStatus: 'draft',
      isArchived: false,
      actorPrincipal: 'test',
      correlationId: 'corr-1'
    })

    expect(bundle.schema_id).toBe('EngineeringInputBundleV1')
    expect(bundle.equipment_inputs.condensing_temperature_c.state).toBe('provided')
    expect(bundle.zone_planning_inputs.daily_inbound_mass_kg.unit).toBe('kg/day')
    expect(bundle.source_metadata.input_group_provenance.zone_planning_inputs).toBe('user_entry')
    expect(bundle.source_metadata.input_group_provenance.investment_inputs).toBe('user_entry')
  })

  it('sets persisted_upstream_confirmed only when user confirms lineage', () => {
    const form = createDefaultEngineeringInputFormState()
    form.confirmPersistedLineage = true
    const bundle = buildEngineeringInputBundle(form, {
      projectId: 'proj-1',
      projectVersionId: 'ver-1',
      versionNumber: 1,
      versionStatus: 'draft',
      isArchived: false,
      actorPrincipal: 'test',
      correlationId: 'corr-1'
    })
    expect(bundle.source_metadata.input_group_provenance.investment_inputs).toBe(
      'persisted_upstream_confirmed'
    )
  })

  it('maps server field_path to camelCase form keys', () => {
    expect(fieldPathToFormKey('cooling_load_inputs.zones[0].zone_area')).toBe(
      'coolingZones.0.zoneArea'
    )
    expect(fieldPathToFormKey('equipment_inputs.condensing_temperature_c')).toBe(
      'equipment.condensingTemperatureC'
    )
  })
})

describe('mapFiveStageProgress', () => {
  it('reports missing stages when canonical chain incomplete', () => {
    const progress = mapFiveStageProgress([
      fiveStageRecord('cold_room_zone_plan')
    ])
    expect(progress.completedCount).toBe(1)
    expect(progress.chainComplete).toBe(false)
    expect(progress.hasPartialChain).toBe(true)
    expect(progress.slots.find((slot) => slot.stage === 'cooling_load')?.status).toBe('partial')
  })

  it('reports complete chain when all five canonical calculators present', () => {
    const progress = mapFiveStageProgress([
      fiveStageRecord('cold_room_zone_plan'),
      fiveStageRecord('cooling_load', {
        upstream_calculation_ids: { zone: 'calc-cold_room_zone_plan' }
      }),
      fiveStageRecord('equipment', {
        upstream_calculation_ids: { cooling_load: 'calc-cooling_load' }
      }),
      fiveStageRecord('installed_power', {
        result_snapshot: {
          success: true,
          calculator_name: 'installed_power',
          calculator_version: '1.0.0',
          input: {},
          result: { total_installed_power_kw_e: 150 }
        },
        upstream_calculation_ids: { equipment: 'calc-equipment' }
      }),
      fiveStageRecord('investment_estimate', {
        upstream_calculation_ids: { zone: 'calc-cold_room_zone_plan', power: 'calc-installed_power' }
      })
    ])
    expect(progress.chainComplete).toBe(true)
    expect(progress.slots.every((slot) => slot.status === 'present')).toBe(true)
  })

  it('keeps power_configuration as supplemental only', () => {
    const progress = mapFiveStageProgress([
      fiveStageRecord('power_configuration'),
      fiveStageRecord('installed_power')
    ])
    const powerSlot = progress.slots.find((slot) => slot.stage === 'power')
    expect(powerSlot?.calculatorName).toBe('installed_power')
    expect(progress.supplementalPowerConfiguration?.calculator_name).toBe('power_configuration')
  })
})
