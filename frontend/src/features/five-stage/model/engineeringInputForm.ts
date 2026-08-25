import type { EngineeringInputBundleV1 } from '../../../api/contracts/fiveStage'
import { bundleLeaf, bundleNumericLeaf } from './bundleLeaf'

export interface CoolingZoneFormState {
  zoneCode: string
  zoneName: string
  temperatureLevel: string
  zoneArea: number
  roomHeight: number
  wallArea: number
  roofArea: number
  floorArea: number
  outdoorDesignTemperature: number
  roomDesignTemperature: number
  operatingHoursPerDay: number
  productMassPerDay: number
  productEntryTemperature: number
  productTargetTemperature: number
  coolingDuration: number
  uValueWall: number
  uValueRoof: number
  uValueFloor: number
  productSpecificHeat: number
}

export interface EquipmentZoneFormState {
  zoneCode: string
  zoneName: string
  evaporatorCount: number
  defrostMethod: string
  designCoolingLoadKwR: number
}

export interface EquipmentSystemFormState {
  systemCode: string
  systemName: string
  designEvaporatingTemperature: number
  zones: EquipmentZoneFormState[]
}

export interface EngineeringInputFormState {
  zonePlanning: {
    dailyInboundMassKg: number
    workingTimeHPerDay: number
    finishedStorageDays: number
    packagingStorageDays: number
    precoolingRequiredRatio: number
  }
  coolingZones: CoolingZoneFormState[]
  coolingCoefficients: Record<string, string>
  equipment: {
    condensingTemperatureC: number
    systems: EquipmentSystemFormState[]
    coefficients: Record<string, string>
  }
  installedPower: {
    compressorInputPowerKwE: number
    evaporatorFanPowerKwE: number
    condenserFanPowerKwE: number
    pumpPowerKwE: number | null
    defrostPowerKwE: number | null
    processingEquipmentPowerKwE: number | null
    lightingPowerKwE: number | null
    otherAuxiliaryPowerKwE: number | null
  }
  investment: {
    totalAreaM2: number
    refrigeratedAreaM2: number
    frozenAreaM2: number
    positionCount: number
    totalPowerKw: number
  }
  coefficientContext: {
    coefficientContextId: string
    approvedRevisionIds: string[]
  }
  confirmPersistedLineage: boolean
}

export interface BuildBundleContext {
  projectId: string
  projectVersionId: string
  versionNumber: number
  versionStatus: string
  isArchived: boolean
  actorPrincipal: string
  correlationId: string
}

const DEFAULT_COOLING_COEFFICIENTS: Record<string, string> = {
  design_margin_ratio: '1.1',
  diversity_factor: '0.85',
  air_change_rate: '0.5',
  respiration_heat: '0.0',
  worker_heat_gain: '0.275',
  motor_efficiency: '0.85'
}

const DEFAULT_EQUIPMENT_COEFFICIENTS: Record<string, string> = {
  redundancy_ratio: '1.0',
  evaporator_capacity_margin: '1.1',
  condenser_capacity_margin: '1.1',
  compressor_cop: '2.5'
}

function createDefaultCoolingZone(): CoolingZoneFormState {
  return {
    zoneCode: 'Z1',
    zoneName: '冷冻库',
    temperatureLevel: 'low_temperature',
    zoneArea: 100,
    roomHeight: 5,
    wallArea: 200,
    roofArea: 100,
    floorArea: 100,
    outdoorDesignTemperature: 30,
    roomDesignTemperature: -18,
    operatingHoursPerDay: 16,
    productMassPerDay: 20000,
    productEntryTemperature: 20,
    productTargetTemperature: -18,
    coolingDuration: 8,
    uValueWall: 0.25,
    uValueRoof: 0.2,
    uValueFloor: 0.3,
    productSpecificHeat: 3.6
  }
}

function createDefaultEquipmentZone(): EquipmentZoneFormState {
  return {
    zoneCode: 'Z1',
    zoneName: '冷冻库',
    evaporatorCount: 2,
    defrostMethod: 'electric',
    designCoolingLoadKwR: 120
  }
}

function createDefaultEquipmentSystem(): EquipmentSystemFormState {
  return {
    systemCode: 'S1',
    systemName: '冷冻系统',
    designEvaporatingTemperature: -25,
    zones: [createDefaultEquipmentZone()]
  }
}

export function createDefaultEngineeringInputFormState(): EngineeringInputFormState {
  return {
    zonePlanning: {
      dailyInboundMassKg: 20000,
      workingTimeHPerDay: 16,
      finishedStorageDays: 7,
      packagingStorageDays: 1,
      precoolingRequiredRatio: 0.6
    },
    coolingZones: [createDefaultCoolingZone()],
    coolingCoefficients: { ...DEFAULT_COOLING_COEFFICIENTS },
    equipment: {
      condensingTemperatureC: 40,
      systems: [createDefaultEquipmentSystem()],
      coefficients: { ...DEFAULT_EQUIPMENT_COEFFICIENTS }
    },
    installedPower: {
      compressorInputPowerKwE: 120,
      evaporatorFanPowerKwE: 10,
      condenserFanPowerKwE: 8,
      pumpPowerKwE: null,
      defrostPowerKwE: null,
      processingEquipmentPowerKwE: null,
      lightingPowerKwE: null,
      otherAuxiliaryPowerKwE: null
    },
    investment: {
      totalAreaM2: 1000,
      refrigeratedAreaM2: 800,
      frozenAreaM2: 200,
      positionCount: 100,
      totalPowerKw: 150
    },
    coefficientContext: {
      coefficientContextId: 'coeff-demo-001',
      approvedRevisionIds: ['rev-001']
    },
    confirmPersistedLineage: false
  }
}

function buildCoolingZoneLeaves(zone: CoolingZoneFormState): Record<string, ReturnType<typeof bundleLeaf>> {
  return {
    zone_code: bundleLeaf(zone.zoneCode, { unit: null }),
    zone_name: bundleLeaf(zone.zoneName, { unit: null }),
    temperature_level: bundleLeaf(zone.temperatureLevel, { unit: null }),
    zone_area: bundleNumericLeaf(zone.zoneArea, { unit: 'm2' }),
    room_height: bundleNumericLeaf(zone.roomHeight, { unit: 'm' }),
    wall_area: bundleNumericLeaf(zone.wallArea, { unit: 'm2' }),
    roof_area: bundleNumericLeaf(zone.roofArea, { unit: 'm2' }),
    floor_area: bundleNumericLeaf(zone.floorArea, { unit: 'm2' }),
    outdoor_design_temperature: bundleNumericLeaf(zone.outdoorDesignTemperature, { unit: 'C' }),
    room_design_temperature: bundleNumericLeaf(zone.roomDesignTemperature, { unit: 'C' }),
    operating_hours_per_day: bundleNumericLeaf(zone.operatingHoursPerDay, { unit: 'h/day' }),
    product_mass_per_day: bundleNumericLeaf(zone.productMassPerDay, { unit: 'kg/day' }),
    product_entry_temperature: bundleNumericLeaf(zone.productEntryTemperature, { unit: 'C' }),
    product_target_temperature: bundleNumericLeaf(zone.productTargetTemperature, { unit: 'C' }),
    cooling_duration: bundleNumericLeaf(zone.coolingDuration, { unit: 'h' }),
    u_value_wall: bundleNumericLeaf(zone.uValueWall, {
      unit: 'W/(m2·K)',
      source_type: 'coefficient'
    }),
    u_value_roof: bundleNumericLeaf(zone.uValueRoof, {
      unit: 'W/(m2·K)',
      source_type: 'coefficient'
    }),
    u_value_floor: bundleNumericLeaf(zone.uValueFloor, {
      unit: 'W/(m2·K)',
      source_type: 'coefficient'
    }),
    product_specific_heat: bundleNumericLeaf(zone.productSpecificHeat, {
      unit: 'kJ/(kg·K)',
      source_type: 'coefficient'
    })
  }
}

function optionalPowerLeaf(value: number | null, unit: string): ReturnType<typeof bundleLeaf> {
  if (value === null || !Number.isFinite(value)) {
    return bundleLeaf(null, { unit, state: 'tentative' })
  }
  return bundleNumericLeaf(value, { unit })
}

export function buildEngineeringInputBundle(
  form: EngineeringInputFormState,
  context: BuildBundleContext
): EngineeringInputBundleV1 {
  const investmentProvenance = form.confirmPersistedLineage
    ? 'persisted_upstream_confirmed'
    : 'user_entry'

  return {
    schema_id: 'EngineeringInputBundleV1',
    schema_version: '1.0.0',
    project_version_identity: {
      project_id: bundleLeaf(context.projectId, {
        source_type: 'persisted',
        validity_status: 'verified',
        requires_review: false
      }),
      project_version_id: bundleLeaf(context.projectVersionId, {
        source_type: 'persisted',
        validity_status: 'verified',
        requires_review: false
      }),
      version_number: bundleLeaf(context.versionNumber, {
        source_type: 'persisted',
        validity_status: 'verified',
        requires_review: false
      }),
      version_status: bundleLeaf(context.versionStatus, {
        source_type: 'persisted',
        validity_status: 'verified',
        requires_review: false
      }),
      is_archived: bundleLeaf(context.isArchived, {
        source_type: 'persisted',
        validity_status: 'verified',
        requires_review: false
      }),
      actor_principal: bundleLeaf(context.actorPrincipal, {
        validity_status: 'verified',
        requires_review: false
      }),
      correlation_id: bundleLeaf(context.correlationId, {
        validity_status: 'verified',
        requires_review: false
      })
    },
    zone_planning_inputs: {
      daily_inbound_mass_kg: bundleNumericLeaf(form.zonePlanning.dailyInboundMassKg, { unit: 'kg/day' }),
      working_time_h_per_day: bundleNumericLeaf(form.zonePlanning.workingTimeHPerDay, { unit: 'h/day' }),
      finished_storage_days: bundleNumericLeaf(form.zonePlanning.finishedStorageDays, { unit: 'day' }),
      packaging_storage_days: bundleNumericLeaf(form.zonePlanning.packagingStorageDays, { unit: 'day' }),
      precooling_required_ratio: bundleNumericLeaf(form.zonePlanning.precoolingRequiredRatio, { unit: 'ratio' })
    },
    cooling_load_inputs: {
      zones: form.coolingZones.map(buildCoolingZoneLeaves),
      coefficients: bundleLeaf(form.coolingCoefficients, {
        unit: null,
        source_type: 'coefficient'
      })
    },
    equipment_inputs: {
      condensing_temperature_c: bundleNumericLeaf(form.equipment.condensingTemperatureC, { unit: 'C' }),
      systems: form.equipment.systems.map((system) => ({
        system_code: bundleLeaf(system.systemCode, { unit: null }),
        system_name: bundleLeaf(system.systemName, { unit: null }),
        design_evaporating_temperature: bundleNumericLeaf(system.designEvaporatingTemperature, { unit: 'C' }),
        zones: system.zones.map((zone) => ({
          zone_code: bundleLeaf(zone.zoneCode, { unit: null }),
          zone_name: bundleLeaf(zone.zoneName, { unit: null }),
          evaporator_count: bundleLeaf(zone.evaporatorCount, { unit: 'count' }),
          defrost_method: bundleLeaf(zone.defrostMethod, { unit: null }),
          design_cooling_load_kw_r: bundleNumericLeaf(zone.designCoolingLoadKwR, {
            unit: 'kW(r)',
            source_type: 'persisted'
          })
        }))
      })),
      coefficients: bundleLeaf(form.equipment.coefficients, {
        unit: null,
        source_type: 'coefficient'
      })
    },
    installed_power_inputs: {
      compressor_input_power_kw_e: bundleNumericLeaf(form.installedPower.compressorInputPowerKwE, {
        unit: 'kW(e)'
      }),
      evaporator_fan_power_kw_e: bundleNumericLeaf(form.installedPower.evaporatorFanPowerKwE, {
        unit: 'kW(e)'
      }),
      condenser_fan_power_kw_e: bundleNumericLeaf(form.installedPower.condenserFanPowerKwE, {
        unit: 'kW(e)'
      }),
      pump_power_kw_e: optionalPowerLeaf(form.installedPower.pumpPowerKwE, 'kW(e)'),
      defrost_power_kw_e: optionalPowerLeaf(form.installedPower.defrostPowerKwE, 'kW(e)'),
      processing_equipment_power_kw_e: optionalPowerLeaf(
        form.installedPower.processingEquipmentPowerKwE,
        'kW(e)'
      ),
      lighting_power_kw_e: optionalPowerLeaf(form.installedPower.lightingPowerKwE, 'kW(e)'),
      other_auxiliary_power_kw_e: optionalPowerLeaf(form.installedPower.otherAuxiliaryPowerKwE, 'kW(e)')
    },
    investment_inputs: {
      total_area_m2: bundleNumericLeaf(form.investment.totalAreaM2, {
        unit: 'm2',
        source_type: form.confirmPersistedLineage ? 'persisted' : 'user'
      }),
      refrigerated_area_m2: bundleNumericLeaf(form.investment.refrigeratedAreaM2, {
        unit: 'm2',
        source_type: form.confirmPersistedLineage ? 'persisted' : 'user'
      }),
      frozen_area_m2: bundleNumericLeaf(form.investment.frozenAreaM2, {
        unit: 'm2',
        source_type: form.confirmPersistedLineage ? 'persisted' : 'user'
      }),
      position_count: bundleLeaf(form.investment.positionCount, {
        unit: 'count',
        source_type: form.confirmPersistedLineage ? 'persisted' : 'user'
      }),
      total_power_kw: bundleNumericLeaf(form.investment.totalPowerKw, {
        unit: 'kW(e)',
        source_type: form.confirmPersistedLineage ? 'persisted' : 'user'
      })
    },
    coefficient_context: {
      coefficient_context_id: bundleLeaf(form.coefficientContext.coefficientContextId, {
        source_type: 'coefficient'
      }),
      approved_revision_ids: bundleLeaf(form.coefficientContext.approvedRevisionIds, {
        source_type: 'coefficient'
      }),
      demo_coefficient_leaves: []
    },
    units_metadata: {
      leaf_unit_by_path: {
        'zone_planning_inputs.daily_inbound_mass_kg': 'kg/day',
        'cooling_load_inputs.zones[0].zone_area': 'm2',
        'equipment_inputs.condensing_temperature_c': 'C',
        'installed_power_inputs.compressor_input_power_kw_e': 'kW(e)'
      }
    },
    source_metadata: {
      input_group_provenance: {
        zone_planning_inputs: 'user_entry',
        cooling_load_inputs: 'user_entry',
        equipment_inputs: 'user_entry',
        installed_power_inputs: 'user_entry',
        investment_inputs: investmentProvenance
      }
    },
    review_metadata: {
      overall_requires_review: bundleLeaf(true, { unit: null }),
      per_group_requires_review: {
        zone_planning_inputs: true,
        cooling_load_inputs: true,
        equipment_inputs: true,
        installed_power_inputs: true,
        investment_inputs: true
      }
    }
  }
}

export function stableBundlePayloadJson(bundle: EngineeringInputBundleV1): string {
  return JSON.stringify(bundle)
}

export function fieldPathToFormKey(fieldPath: string): string | null {
  const snakeToCamelSegment = (segment: string): string =>
    segment.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())

  const mappings: Array<[RegExp, string]> = [
    [/^zone_planning_inputs\.(\w+)$/, 'zonePlanning.$1'],
    [/^cooling_load_inputs\.zones\[(\d+)\]\.(\w+)$/, 'coolingZones.$1.$2'],
    [/^equipment_inputs\.condensing_temperature_c$/, 'equipment.condensingTemperatureC'],
    [/^equipment_inputs\.systems\[(\d+)\]\.(\w+)$/, 'equipment.systems.$1.$2'],
    [
      /^equipment_inputs\.systems\[(\d+)\]\.zones\[(\d+)\]\.(\w+)$/,
      'equipment.systems.$1.zones.$2.$3'
    ],
    [/^installed_power_inputs\.(\w+)$/, 'installedPower.$1'],
    [/^investment_inputs\.(\w+)$/, 'investment.$1']
  ]
  for (const [pattern, template] of mappings) {
    const match = fieldPath.match(pattern)
    if (!match) continue
    let key = template
    for (let index = 1; index < match.length; index += 1) {
      const replacement = /^\d+$/.test(match[index])
        ? match[index]
        : snakeToCamelSegment(match[index])
      key = key.replace(`$${index}`, replacement)
    }
    return key
  }
  return null
}

export function snakeToCamelField(field: string): string {
  return field.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
}

export {
  createDefaultCoolingZone,
  createDefaultEquipmentSystem,
  createDefaultEquipmentZone
}
