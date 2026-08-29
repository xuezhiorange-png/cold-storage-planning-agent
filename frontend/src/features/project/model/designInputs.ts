import type { PlanningRunRequest } from '../../../api/contracts/planning'
import { operatorDemoZoneNumeric } from '../../design-inputs/operatorDemoDefaults'

/** Demo migration gap defaults — must be persisted via project inputs, not silent authority. */
export const DEMO_MIGRATION_GAP_COEFFICIENTS = {
  utilization_factor: 0.85,
  reserve_factor: 1.05
} as const

export interface DesignInputs {
  dailyInboundMassTons: number
  workingHoursPerDay: number
  utilizationFactor: number
  reserveFactor: number
  finishedStorageDays: number
  packagingStorageDays: number
  auxiliaryPackagingStorageDays: number
  precoolingRequiredRatio: number
  rawStorageRatio: number
  primaryPrecoolingWorkingHours: number
  secondaryPrecoolingWorkingHours: number
  finishedGoodsPalletWeightKg: number
  frozenFruitRatio: number
  frozenStorageDays: number
  frozenGoodsPalletWeightKg: number
}

export interface DesignInputValidationError {
  field: keyof DesignInputs
  message: string
}

export function createDefaultDesignInputs(): DesignInputs {
  return {
    dailyInboundMassTons: operatorDemoZoneNumeric('daily_inbound_mass_kg') / 1000,
    workingHoursPerDay: 16,
    utilizationFactor: DEMO_MIGRATION_GAP_COEFFICIENTS.utilization_factor,
    reserveFactor: DEMO_MIGRATION_GAP_COEFFICIENTS.reserve_factor,
    finishedStorageDays: operatorDemoZoneNumeric('finished_storage_days'),
    packagingStorageDays: operatorDemoZoneNumeric('main_packaging_storage_days'),
    auxiliaryPackagingStorageDays: operatorDemoZoneNumeric('auxiliary_packaging_storage_days'),
    precoolingRequiredRatio: 1,
    rawStorageRatio: 0.4,
    primaryPrecoolingWorkingHours: 6,
    secondaryPrecoolingWorkingHours: 16,
    finishedGoodsPalletWeightKg: 400,
    frozenFruitRatio: 0.1,
    frozenStorageDays: operatorDemoZoneNumeric('frozen_storage_days'),
    frozenGoodsPalletWeightKg: 600
  }
}

export function validateDesignInputs(inputs: DesignInputs): DesignInputValidationError[] {
  const errors: DesignInputValidationError[] = []
  const positiveFields: Array<keyof DesignInputs> = [
    'dailyInboundMassTons',
    'workingHoursPerDay',
    'reserveFactor',
    'finishedStorageDays',
    'packagingStorageDays',
    'auxiliaryPackagingStorageDays',
    'primaryPrecoolingWorkingHours',
    'secondaryPrecoolingWorkingHours',
    'finishedGoodsPalletWeightKg',
    'frozenStorageDays',
    'frozenGoodsPalletWeightKg'
  ]

  for (const field of positiveFields) {
    if (!Number.isFinite(inputs[field]) || inputs[field] <= 0) {
      errors.push({ field, message: '必须大于 0' })
    }
  }

  if (
    !Number.isFinite(inputs.utilizationFactor) ||
    inputs.utilizationFactor <= 0 ||
    inputs.utilizationFactor > 1
  ) {
    errors.push({ field: 'utilizationFactor', message: '必须在 0 到 1 之间' })
  }

  const ratioFields: Array<keyof DesignInputs> = [
    'precoolingRequiredRatio',
    'rawStorageRatio',
    'frozenFruitRatio'
  ]
  for (const field of ratioFields) {
    if (!Number.isFinite(inputs[field]) || inputs[field] < 0 || inputs[field] > 1) {
      errors.push({ field, message: '必须在 0 到 1 之间' })
    }
  }

  return errors
}

export function mapDesignInputsToPlanningRequest(inputs: DesignInputs): PlanningRunRequest {
  return {
    daily_inbound_mass_kg: inputs.dailyInboundMassTons * 1000,
    working_time_h_per_day: inputs.workingHoursPerDay,
    utilization_factor: inputs.utilizationFactor,
    finished_storage_days: inputs.finishedStorageDays,
    packaging_storage_days: inputs.packagingStorageDays,
    main_packaging_storage_days: inputs.packagingStorageDays,
    auxiliary_packaging_storage_days: inputs.auxiliaryPackagingStorageDays,
    reserve_factor: inputs.reserveFactor,
    precooling_required_ratio: inputs.precoolingRequiredRatio,
    primary_precooling_working_hours_per_day: inputs.primaryPrecoolingWorkingHours,
    secondary_precooling_working_hours_per_day: inputs.secondaryPrecoolingWorkingHours,
    raw_storage_ratio: inputs.rawStorageRatio,
    finished_goods_pallet_weight_kg: inputs.finishedGoodsPalletWeightKg,
    frozen_fruit_ratio: inputs.frozenFruitRatio,
    frozen_storage_days: inputs.frozenStorageDays,
    frozen_goods_pallet_weight_kg: inputs.frozenGoodsPalletWeightKg
  }
}

export function mapPersistedInputsToDesignInputs(
  snapshot: Record<string, unknown>
): Partial<DesignInputs> {
  const partial: Partial<DesignInputs> = {}
  if (typeof snapshot.daily_inbound_mass_kg === 'number') {
    partial.dailyInboundMassTons = snapshot.daily_inbound_mass_kg / 1000
  }
  if (typeof snapshot.working_time_h_per_day === 'number') {
    partial.workingHoursPerDay = snapshot.working_time_h_per_day
  }
  if (typeof snapshot.utilization_factor === 'number') {
    partial.utilizationFactor = snapshot.utilization_factor
  }
  if (typeof snapshot.reserve_factor === 'number') {
    partial.reserveFactor = snapshot.reserve_factor
  }
  if (typeof snapshot.finished_storage_days === 'number') {
    partial.finishedStorageDays = snapshot.finished_storage_days
  }
  if (typeof snapshot.packaging_storage_days === 'number') {
    partial.packagingStorageDays = snapshot.packaging_storage_days
  }
  if (typeof snapshot.auxiliary_packaging_storage_days === 'number') {
    partial.auxiliaryPackagingStorageDays = snapshot.auxiliary_packaging_storage_days
  }
  if (typeof snapshot.precooling_required_ratio === 'number') {
    partial.precoolingRequiredRatio = snapshot.precooling_required_ratio
  }
  if (typeof snapshot.raw_storage_ratio === 'number') {
    partial.rawStorageRatio = snapshot.raw_storage_ratio
  }
  if (typeof snapshot.primary_precooling_working_hours_per_day === 'number') {
    partial.primaryPrecoolingWorkingHours = snapshot.primary_precooling_working_hours_per_day
  }
  if (typeof snapshot.secondary_precooling_working_hours_per_day === 'number') {
    partial.secondaryPrecoolingWorkingHours = snapshot.secondary_precooling_working_hours_per_day
  }
  if (typeof snapshot.finished_goods_pallet_weight_kg === 'number') {
    partial.finishedGoodsPalletWeightKg = snapshot.finished_goods_pallet_weight_kg
  }
  if (typeof snapshot.frozen_fruit_ratio === 'number') {
    partial.frozenFruitRatio = snapshot.frozen_fruit_ratio
  }
  if (typeof snapshot.frozen_storage_days === 'number') {
    partial.frozenStorageDays = snapshot.frozen_storage_days
  }
  if (typeof snapshot.frozen_goods_pallet_weight_kg === 'number') {
    partial.frozenGoodsPalletWeightKg = snapshot.frozen_goods_pallet_weight_kg
  }
  return partial
}
