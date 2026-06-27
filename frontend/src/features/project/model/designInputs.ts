import type { PlanningRunRequest } from '../../../api/contracts/planning'

export interface DesignInputs {
  dailyInboundMassTons: number
  workingHoursPerDay: number
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
    dailyInboundMassTons: 25,
    workingHoursPerDay: 16,
    finishedStorageDays: 2.5,
    packagingStorageDays: 3,
    auxiliaryPackagingStorageDays: 30,
    precoolingRequiredRatio: 1,
    rawStorageRatio: 0.4,
    primaryPrecoolingWorkingHours: 6,
    secondaryPrecoolingWorkingHours: 16,
    finishedGoodsPalletWeightKg: 400,
    frozenFruitRatio: 0.1,
    frozenStorageDays: 5,
    frozenGoodsPalletWeightKg: 600
  }
}

export function validateDesignInputs(inputs: DesignInputs): DesignInputValidationError[] {
  const errors: DesignInputValidationError[] = []
  const positiveFields: Array<keyof DesignInputs> = [
    'dailyInboundMassTons',
    'workingHoursPerDay',
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
    utilization_factor: 0.85,
    finished_storage_days: inputs.finishedStorageDays,
    packaging_storage_days: inputs.packagingStorageDays,
    main_packaging_storage_days: inputs.packagingStorageDays,
    auxiliary_packaging_storage_days: inputs.auxiliaryPackagingStorageDays,
    reserve_factor: 1.05,
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
