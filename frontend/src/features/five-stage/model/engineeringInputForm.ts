import type { EngineeringInputBundleV1, OperatorProcessInputV1 } from '../../../api/contracts/fiveStage'
import { bundleLeaf, bundleLeafFromInput, bundleNumericLeaf } from './bundleLeaf'

export interface CoolingZoneFormState {
  zoneCode: string
  zoneName: string
  temperatureLevel: string
  zoneArea: number | null
  roomHeight: number | null
  wallArea: number | null
  roofArea: number | null
  floorArea: number | null
  outdoorDesignTemperature: number | null
  roomDesignTemperature: number | null
  operatingHoursPerDay: number | null
  productMassPerDay: number | null
  productEntryTemperature: number | null
  productTargetTemperature: number | null
  coolingDuration: number | null
  uValueWall: number | null
  uValueRoof: number | null
  uValueFloor: number | null
  productSpecificHeat: number | null
}

export interface EquipmentZoneFormState {
  zoneCode: string
  zoneName: string
  evaporatorCount: number | null
  defrostMethod: string
  designCoolingLoadKwR: number | null
}

export interface EquipmentSystemFormState {
  systemCode: string
  systemName: string
  designEvaporatingTemperature: number | null
  zones: EquipmentZoneFormState[]
}

export interface EngineeringInputFormState {
  zonePlanning: {
    dailyInboundMassKg: number | null
    workingTimeHPerDay: number | null
    finishedStorageDays: number | null
    packagingStorageDays: number | null
    precoolingRequiredRatio: number | null
  }
  coolingZones: CoolingZoneFormState[]
  coolingCoefficients: Record<string, string>
  equipment: {
    condensingTemperatureC: number | null
    systems: EquipmentSystemFormState[]
    coefficients: Record<string, string>
  }
  installedPower: {
    compressorInputPowerKwE: number | null
    evaporatorFanPowerKwE: number | null
    condenserFanPowerKwE: number | null
    pumpPowerKwE: number | null
    defrostPowerKwE: number | null
    processingEquipmentPowerKwE: number | null
    lightingPowerKwE: number | null
    otherAuxiliaryPowerKwE: number | null
  }
  investment: {
    totalAreaM2: number | null
    refrigeratedAreaM2: number | null
    frozenAreaM2: number | null
    positionCount: number | null
    totalPowerKw: number | null
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

/** Caller-supplied context before request-scoped correlation_id is resolved. */
export type SubmitBundleContext = Omit<BuildBundleContext, 'correlationId'>

/** Demo coefficient leaves — coefficient source only, never authoritative user input. */
const DEMO_COOLING_COEFFICIENTS: Record<string, string> = {
  design_margin_ratio: '1.1',
  diversity_factor: '0.85',
  air_change_rate: '0.5',
  respiration_heat: '0.0',
  worker_heat_gain: '0.275',
  motor_efficiency: '0.85'
}

const DEMO_EQUIPMENT_COEFFICIENTS: Record<string, string> = {
  redundancy_ratio: '1.0',
  evaporator_capacity_margin: '1.1',
  condenser_capacity_margin: '1.1',
  compressor_cop: '2.5'
}

const COEFFICIENT_LEAF_OPTIONS = {
  source_type: 'coefficient' as const,
  validity_status: 'unverified' as const,
  requires_review: true
}

function createDefaultCoolingZone(): CoolingZoneFormState {
  return {
    zoneCode: '',
    zoneName: '',
    temperatureLevel: '',
    zoneArea: null,
    roomHeight: null,
    wallArea: null,
    roofArea: null,
    floorArea: null,
    outdoorDesignTemperature: null,
    roomDesignTemperature: null,
    operatingHoursPerDay: null,
    productMassPerDay: null,
    productEntryTemperature: null,
    productTargetTemperature: null,
    coolingDuration: null,
    uValueWall: null,
    uValueRoof: null,
    uValueFloor: null,
    productSpecificHeat: null
  }
}

function createDefaultEquipmentZone(): EquipmentZoneFormState {
  return {
    zoneCode: '',
    zoneName: '',
    evaporatorCount: null,
    defrostMethod: '',
    designCoolingLoadKwR: null
  }
}

function createDefaultEquipmentSystem(): EquipmentSystemFormState {
  return {
    systemCode: '',
    systemName: '',
    designEvaporatingTemperature: null,
    zones: [createDefaultEquipmentZone()]
  }
}

export function createDefaultEngineeringInputFormState(): EngineeringInputFormState {
  return {
    zonePlanning: {
      dailyInboundMassKg: null,
      workingTimeHPerDay: null,
      finishedStorageDays: null,
      packagingStorageDays: null,
      precoolingRequiredRatio: null
    },
    coolingZones: [createDefaultCoolingZone()],
    coolingCoefficients: { ...DEMO_COOLING_COEFFICIENTS },
    equipment: {
      condensingTemperatureC: null,
      systems: [createDefaultEquipmentSystem()],
      coefficients: { ...DEMO_EQUIPMENT_COEFFICIENTS }
    },
    installedPower: {
      compressorInputPowerKwE: null,
      evaporatorFanPowerKwE: null,
      condenserFanPowerKwE: null,
      pumpPowerKwE: null,
      defrostPowerKwE: null,
      processingEquipmentPowerKwE: null,
      lightingPowerKwE: null,
      otherAuxiliaryPowerKwE: null
    },
    investment: {
      totalAreaM2: null,
      refrigeratedAreaM2: null,
      frozenAreaM2: null,
      positionCount: null,
      totalPowerKw: null
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
    zone_code: bundleLeafFromInput(zone.zoneCode, { unit: null }),
    zone_name: bundleLeafFromInput(zone.zoneName, { unit: null }),
    temperature_level: bundleLeafFromInput(zone.temperatureLevel, { unit: null }),
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
      ...COEFFICIENT_LEAF_OPTIONS
    }),
    u_value_roof: bundleNumericLeaf(zone.uValueRoof, {
      unit: 'W/(m2·K)',
      ...COEFFICIENT_LEAF_OPTIONS
    }),
    u_value_floor: bundleNumericLeaf(zone.uValueFloor, {
      unit: 'W/(m2·K)',
      ...COEFFICIENT_LEAF_OPTIONS
    }),
    product_specific_heat: bundleNumericLeaf(zone.productSpecificHeat, {
      unit: 'kJ/(kg·K)',
      ...COEFFICIENT_LEAF_OPTIONS
    })
  }
}

function optionalPowerLeaf(value: number | null, unit: string): ReturnType<typeof bundleLeaf> {
  if (value === null || !Number.isFinite(value)) {
    return bundleLeaf(null, { unit, state: 'tentative' })
  }
  return bundleNumericLeaf(value, { unit })
}

export function buildOperatorProcessInput(form: EngineeringInputFormState): OperatorProcessInputV1 {
  return {
    schema_id: 'OperatorProcessInputV1',
    schema_version: '1.0.0',
    zone_planning_inputs: {
      daily_inbound_mass_kg: bundleNumericLeaf(form.zonePlanning.dailyInboundMassKg, { unit: 'kg/day' }),
      working_time_h_per_day: bundleNumericLeaf(form.zonePlanning.workingTimeHPerDay, { unit: 'h/day' }),
      finished_storage_days: bundleNumericLeaf(form.zonePlanning.finishedStorageDays, { unit: 'day' }),
      packaging_storage_days: bundleNumericLeaf(form.zonePlanning.packagingStorageDays, { unit: 'day' }),
      precooling_required_ratio: bundleNumericLeaf(form.zonePlanning.precoolingRequiredRatio, { unit: 'ratio' })
    }
  }
}

export function stableOperatorProcessFieldsJson(form: EngineeringInputFormState): string {
  const zonePlanning = form.zonePlanning
  return JSON.stringify({
    daily_inbound_mass_kg: zonePlanning.dailyInboundMassKg,
    working_time_h_per_day: zonePlanning.workingTimeHPerDay,
    finished_storage_days: zonePlanning.finishedStorageDays,
    packaging_storage_days: zonePlanning.packagingStorageDays,
    precooling_required_ratio: zonePlanning.precoolingRequiredRatio
  })
}

export function stableOperatorProcessPayloadJson(payload: OperatorProcessInputV1): string {
  return JSON.stringify(payload)
}

export function buildEngineeringInputBundle(
  form: EngineeringInputFormState,
  context: BuildBundleContext
): EngineeringInputBundleV1 {
  const lineageProvenance = form.confirmPersistedLineage
    ? 'persisted_upstream_confirmed'
    : 'user_entry'
  const persistedLineageSource = form.confirmPersistedLineage ? 'persisted' : 'user'

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
        ...COEFFICIENT_LEAF_OPTIONS
      })
    },
    equipment_inputs: {
      condensing_temperature_c: bundleNumericLeaf(form.equipment.condensingTemperatureC, { unit: 'C' }),
      systems: form.equipment.systems.map((system) => ({
        system_code: bundleLeafFromInput(system.systemCode, { unit: null }),
        system_name: bundleLeafFromInput(system.systemName, { unit: null }),
        design_evaporating_temperature: bundleNumericLeaf(system.designEvaporatingTemperature, { unit: 'C' }),
        zones: system.zones.map((zone) => ({
          zone_code: bundleLeafFromInput(zone.zoneCode, { unit: null }),
          zone_name: bundleLeafFromInput(zone.zoneName, { unit: null }),
          evaporator_count: bundleNumericLeaf(zone.evaporatorCount, { unit: 'count' }),
          defrost_method: bundleLeafFromInput(zone.defrostMethod, { unit: null }),
          design_cooling_load_kw_r: bundleNumericLeaf(zone.designCoolingLoadKwR, {
            unit: 'kW(r)',
            source_type: persistedLineageSource
          })
        }))
      })),
      coefficients: bundleLeaf(form.equipment.coefficients, {
        unit: null,
        ...COEFFICIENT_LEAF_OPTIONS
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
        source_type: persistedLineageSource
      }),
      refrigerated_area_m2: bundleNumericLeaf(form.investment.refrigeratedAreaM2, {
        unit: 'm2',
        source_type: persistedLineageSource
      }),
      frozen_area_m2: bundleNumericLeaf(form.investment.frozenAreaM2, {
        unit: 'm2',
        source_type: persistedLineageSource
      }),
      position_count: bundleNumericLeaf(form.investment.positionCount, {
        unit: 'count',
        source_type: persistedLineageSource
      }),
      total_power_kw: bundleNumericLeaf(form.investment.totalPowerKw, {
        unit: 'kW(e)',
        source_type: persistedLineageSource
      })
    },
    coefficient_context: {
      coefficient_context_id: bundleLeaf(form.coefficientContext.coefficientContextId, {
        ...COEFFICIENT_LEAF_OPTIONS
      }),
      approved_revision_ids: bundleLeaf(form.coefficientContext.approvedRevisionIds, {
        ...COEFFICIENT_LEAF_OPTIONS
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
        equipment_inputs: lineageProvenance,
        installed_power_inputs: 'user_entry',
        investment_inputs: lineageProvenance
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

/** Canonical JSON of user-entered engineering fields only (excludes request identity). */
export function stableEngineeringFieldsJson(form: EngineeringInputFormState): string {
  return JSON.stringify(form)
}

export function buildWorkbenchSubmitContext(params: {
  projectId: string
  projectVersionId: string
  versionNumber: number
  versionStatus: string
  isArchived: boolean
  actorPrincipal?: string
}): SubmitBundleContext {
  return {
    projectId: params.projectId,
    projectVersionId: params.projectVersionId,
    versionNumber: params.versionNumber,
    versionStatus: params.versionStatus,
    isArchived: params.isArchived,
    actorPrincipal: params.actorPrincipal ?? 'workbench-user'
  }
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
