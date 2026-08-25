import { describe, expect, it } from 'vitest'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import {
  buildEngineeringInputBundle,
  createDefaultEngineeringInputFormState,
  fieldPathToFormKey
} from './engineeringInputForm'
import { mapFiveStageProgress } from './mapFiveStageCalculations'

const BUNDLE_CONTEXT = {
  projectId: 'proj-1',
  projectVersionId: 'ver-1',
  versionNumber: 1,
  versionStatus: 'draft',
  isArchived: false,
  actorPrincipal: 'test',
  correlationId: 'corr-1'
}

function filledEngineeringInputFormState() {
  const form = createDefaultEngineeringInputFormState()
  form.zonePlanning.dailyInboundMassKg = 20000
  form.zonePlanning.workingTimeHPerDay = 16
  form.zonePlanning.finishedStorageDays = 7
  form.zonePlanning.packagingStorageDays = 1
  form.zonePlanning.precoolingRequiredRatio = 0.6
  const zone = form.coolingZones[0]
  zone.zoneCode = 'Z1'
  zone.zoneName = '冷冻库'
  zone.temperatureLevel = 'low_temperature'
  zone.zoneArea = 100
  zone.roomHeight = 5
  zone.wallArea = 200
  zone.roofArea = 100
  zone.floorArea = 100
  zone.outdoorDesignTemperature = 30
  zone.roomDesignTemperature = -18
  zone.operatingHoursPerDay = 16
  zone.productMassPerDay = 20000
  zone.productEntryTemperature = 20
  zone.productTargetTemperature = -18
  zone.coolingDuration = 8
  zone.uValueWall = 0.25
  zone.uValueRoof = 0.2
  zone.uValueFloor = 0.3
  zone.productSpecificHeat = 3.6
  form.equipment.condensingTemperatureC = 40
  const system = form.equipment.systems[0]
  system.systemCode = 'S1'
  system.systemName = '冷冻系统'
  system.designEvaporatingTemperature = -25
  const eqZone = system.zones[0]
  eqZone.zoneCode = 'Z1'
  eqZone.zoneName = '冷冻库'
  eqZone.evaporatorCount = 2
  eqZone.defrostMethod = 'electric'
  eqZone.designCoolingLoadKwR = 120
  form.installedPower.compressorInputPowerKwE = 120
  form.installedPower.evaporatorFanPowerKwE = 10
  form.installedPower.condenserFanPowerKwE = 8
  form.investment.totalAreaM2 = 1000
  form.investment.refrigeratedAreaM2 = 800
  form.investment.frozenAreaM2 = 200
  form.investment.positionCount = 100
  form.investment.totalPowerKw = 150
  return form
}

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
  it('leaves default KEY numeric fields empty and posts state=missing', () => {
    const form = createDefaultEngineeringInputFormState()

    expect(form.zonePlanning.dailyInboundMassKg).toBeNull()
    expect(form.equipment.condensingTemperatureC).toBeNull()
    expect(form.installedPower.compressorInputPowerKwE).toBeNull()
    expect(form.coolingZones[0].zoneArea).toBeNull()
    expect(form.equipment.systems[0].zones[0].designCoolingLoadKwR).toBeNull()

    const bundle = buildEngineeringInputBundle(form, BUNDLE_CONTEXT)

    expect(bundle.zone_planning_inputs.daily_inbound_mass_kg.state).toBe('missing')
    expect(bundle.equipment_inputs.condensing_temperature_c.state).toBe('missing')
    expect(bundle.installed_power_inputs.compressor_input_power_kw_e.state).toBe('missing')
    expect(bundle.cooling_load_inputs.zones[0].zone_area.state).toBe('missing')
    expect(
      bundle.equipment_inputs.systems[0].zones[0].design_cooling_load_kw_r.state
    ).toBe('missing')
    expect(bundle.zone_planning_inputs.daily_inbound_mass_kg.source_type).toBe('user')
  })

  it('keeps coefficient-context demo IDs as coefficient/unverified', () => {
    const bundle = buildEngineeringInputBundle(createDefaultEngineeringInputFormState(), BUNDLE_CONTEXT)

    expect(bundle.coefficient_context.coefficient_context_id.source_type).toBe('coefficient')
    expect(bundle.coefficient_context.coefficient_context_id.validity_status).toBe('unverified')
    expect(bundle.coefficient_context.coefficient_context_id.requires_review).toBe(true)
    expect(bundle.cooling_load_inputs.coefficients.source_type).toBe('coefficient')
    expect(bundle.equipment_inputs.coefficients.source_type).toBe('coefficient')
  })

  it('builds bundle with user-provided KEY leaves when filled', () => {
    const bundle = buildEngineeringInputBundle(filledEngineeringInputFormState(), BUNDLE_CONTEXT)

    expect(bundle.schema_id).toBe('EngineeringInputBundleV1')
    expect(bundle.equipment_inputs.condensing_temperature_c.state).toBe('provided')
    expect(bundle.zone_planning_inputs.daily_inbound_mass_kg.unit).toBe('kg/day')
    expect(bundle.source_metadata.input_group_provenance.zone_planning_inputs).toBe('user_entry')
    expect(bundle.source_metadata.input_group_provenance.investment_inputs).toBe('user_entry')
    expect(bundle.source_metadata.input_group_provenance.equipment_inputs).toBe('user_entry')
  })

  it('uses user source_type for design_cooling_load_kw_r when lineage not confirmed', () => {
    const form = filledEngineeringInputFormState()
    form.confirmPersistedLineage = false
    const bundle = buildEngineeringInputBundle(form, BUNDLE_CONTEXT)

    expect(bundle.source_metadata.input_group_provenance.equipment_inputs).toBe('user_entry')
    expect(bundle.source_metadata.input_group_provenance.investment_inputs).toBe('user_entry')
    expect(
      bundle.equipment_inputs.systems[0].zones[0].design_cooling_load_kw_r.source_type
    ).toBe('user')
  })

  it('uses persisted lineage for equipment and investment when confirmed', () => {
    const form = filledEngineeringInputFormState()
    form.confirmPersistedLineage = true
    const bundle = buildEngineeringInputBundle(form, BUNDLE_CONTEXT)

    expect(bundle.source_metadata.input_group_provenance.equipment_inputs).toBe(
      'persisted_upstream_confirmed'
    )
    expect(bundle.source_metadata.input_group_provenance.investment_inputs).toBe(
      'persisted_upstream_confirmed'
    )
    expect(
      bundle.equipment_inputs.systems[0].zones[0].design_cooling_load_kw_r.source_type
    ).toBe('persisted')
    expect(bundle.investment_inputs.total_area_m2.source_type).toBe('persisted')
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
