import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import type {
  FactoryPowerCanonicalDetail,
  FactoryPowerCanonicalSummary,
  FactoryPowerPresentation
} from '../../../api/contracts/factoryPower'

export const FACTORY_POWER_CALCULATOR_ID = 'factory_power_estimation'
export const FACTORY_POWER_CALCULATOR_VERSION = '2.0.0-p1'
export const FACTORY_POWER_CALCULATOR_IDENTITY =
  `${FACTORY_POWER_CALCULATOR_ID}@${FACTORY_POWER_CALCULATOR_VERSION}`

const SHA256_HASH_PATTERN = /^sha256:[0-9a-f]{64}$/u

const SUMMARY_FIELDS = [
  'defrost_installed_power_kw',
  'defrost_coincident_power_kw',
  'other_installed_power_kw',
  'other_coincident_power_kw',
  'production_equipment_installed_power_kw',
  'production_equipment_coincident_power_kw',
  'total_installed_power_kw',
  'estimated_total_power_kw'
] as const

export function mapFactoryPowerPresentation(
  records: CalculationRunRecord[]
): FactoryPowerPresentation | null {
  const record = latestFactoryPowerRecord(records)
  if (!record) return null

  const attached = record.factory_power_presentation
  if (!isValidPresentation(attached)) return null
  return clonePresentation(attached)
}

export function latestFactoryPowerRecord(
  records: CalculationRunRecord[]
): CalculationRunRecord | null {
  let latest: CalculationRunRecord | null = null
  for (const record of records) {
    if (
      record.calculator_name === FACTORY_POWER_CALCULATOR_ID
      && record.calculator_version === FACTORY_POWER_CALCULATOR_VERSION
    ) {
      latest = record
    }
  }
  return latest
}

function isValidPresentation(value: unknown): value is FactoryPowerPresentation {
  return (
    isObject(value)
    && value.schema_version === FACTORY_POWER_CALCULATOR_VERSION
    && value.source_calculator_id === FACTORY_POWER_CALCULATOR_ID
    && value.source_calculator_version === FACTORY_POWER_CALCULATOR_VERSION
    && value.source_calculator_identity === FACTORY_POWER_CALCULATOR_IDENTITY
    && typeof value.canonical_result_hash === 'string'
    && SHA256_HASH_PATTERN.test(value.canonical_result_hash)
    && typeof value.factory_area_band === 'string'
    && value.factory_area_band.length > 0
    && isObject(value.unit_semantics)
    && value.unit_semantics.power_unit === 'kW'
    && value.unit_semantics.energy_unit === 'kWh'
    && value.unit_semantics.not_energy === true
    && value.unit_semantics.not_metered_electricity === true
    && value.unit_semantics.not_daily_electricity_consumption === true
    && isObject(value.review)
    && value.review.requires_review === true
    && typeof value.review.status === 'string'
    && value.review.status.length > 0
    && isObject(value.provenance)
    && Array.isArray(value.assumptions)
    && value.assumptions.every((item) => typeof item === 'string' && item.length > 0)
    && Array.isArray(value.details)
    && value.details.every(isValidDetail)
    && isValidSummary(value.summary)
  )
}

function isValidDetail(value: unknown): value is FactoryPowerCanonicalDetail {
  return (
    isObject(value)
    && typeof value.equipment_or_zone === 'string'
    && value.equipment_or_zone.length > 0
    && typeof value.basis === 'string'
    && value.basis.length > 0
    && typeof value.configured_quantity === 'number'
    && Number.isInteger(value.configured_quantity)
    && typeof value.unit_power_kw === 'string'
    && value.unit_power_kw.length > 0
    && typeof value.installed_power_kw === 'string'
    && value.installed_power_kw.length > 0
    && typeof value.pool === 'string'
    && (value.pool === 'POOL_A' || value.pool === 'POOL_B' || value.pool === 'POOL_C')
    && typeof value.simultaneity_factor === 'string'
    && value.simultaneity_factor.length > 0
    && typeof value.coincident_power_kw === 'string'
    && value.coincident_power_kw.length > 0
  )
}

function isValidSummary(value: unknown): value is FactoryPowerCanonicalSummary {
  return (
    isObject(value)
    && SUMMARY_FIELDS.every(
      (field) => typeof value[field] === 'string' && value[field].length > 0
    )
  )
}

function clonePresentation(value: FactoryPowerPresentation): FactoryPowerPresentation {
  return {
    schema_version: value.schema_version,
    source_calculator_id: value.source_calculator_id,
    source_calculator_version: value.source_calculator_version,
    source_calculator_identity: value.source_calculator_identity,
    canonical_result_hash: value.canonical_result_hash,
    factory_area_band: value.factory_area_band,
    unit_semantics: cloneObject(value.unit_semantics),
    review: cloneObject(value.review),
    provenance: cloneObject(value.provenance),
    assumptions: [...value.assumptions],
    details: value.details.map((detail) => ({ ...detail })),
    summary: cloneSummary(value.summary)
  }
}

function cloneSummary(summary: FactoryPowerCanonicalSummary): FactoryPowerCanonicalSummary {
  return {
    defrost_installed_power_kw: summary.defrost_installed_power_kw,
    defrost_coincident_power_kw: summary.defrost_coincident_power_kw,
    other_installed_power_kw: summary.other_installed_power_kw,
    other_coincident_power_kw: summary.other_coincident_power_kw,
    production_equipment_installed_power_kw: summary.production_equipment_installed_power_kw,
    production_equipment_coincident_power_kw: summary.production_equipment_coincident_power_kw,
    total_installed_power_kw: summary.total_installed_power_kw,
    estimated_total_power_kw: summary.estimated_total_power_kw
  }
}

function cloneObject(value: Record<string, unknown>): Record<string, unknown> {
  return { ...value }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
