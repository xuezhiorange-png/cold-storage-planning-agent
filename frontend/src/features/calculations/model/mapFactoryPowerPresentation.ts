import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import type {
  FactoryPowerCanonicalDetail,
  FactoryPowerCanonicalResult,
  FactoryPowerCanonicalSummary,
  FactoryPowerPresentation
} from '../../../api/contracts/factoryPower'

export const FACTORY_POWER_CALCULATOR_ID = 'factory_power_estimation'
export const FACTORY_POWER_CALCULATOR_VERSION = '2.0.0-p1'
export const FACTORY_POWER_CALCULATOR_IDENTITY =
  `${FACTORY_POWER_CALCULATOR_ID}@${FACTORY_POWER_CALCULATOR_VERSION}`

const DETAIL_FIELDS = [
  'equipment_or_zone',
  'basis',
  'configured_quantity',
  'unit_power_kw',
  'installed_power_kw',
  'pool',
  'simultaneity_factor',
  'coincident_power_kw'
] as const

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

const POOL_LABELS: Record<string, string> = {
  POOL_A: '化霜',
  POOL_B: '其他设备',
  POOL_C: '生产设备'
}

const DETAIL_LABELS: Record<string, string> = {
  'public.electric_sliding_door': '冷库电动平移门',
  'public.rapid_rolling_door': '快速卷帘门',
  'public.air_curtain': '风幕',
  'public.loading_platform': '装卸平台',
  'public.ozone_humidification': '臭氧与加湿',
  'public.floor_heating': '地坪加热',
  'cold_storage.lighting': '冷间照明',
  'cold_storage.ultraviolet': '冷间紫外线',
  evaporative_condenser: '蒸发式冷凝器',
  production_equipment: '生产设备'
}

export function mapFactoryPowerPresentation(
  records: CalculationRunRecord[]
): FactoryPowerPresentation | null {
  const record = latestFactoryPowerRecord(records)
  if (!record) return null

  const attached = record.factory_power_presentation
  if (attached && isValidPresentation(attached)) {
    return clonePresentation(attached)
  }

  const canonical = readCanonicalResult(record.result_snapshot)
  if (!canonical || !isValidCanonicalResult(canonical)) return null

  const canonicalHash = readCanonicalHash(record, canonical)
  if (!canonicalHash) return null

  return {
    schema_version: canonical.schema_version,
    source_calculator_id: canonical.calculator.id,
    source_calculator_version: canonical.calculator.version,
    source_calculator_identity: canonical.calculator.identity,
    canonical_result_hash: canonicalHash,
    factory_area_band: canonical.factory_area_band,
    unit_semantics: cloneObject(canonical.unit_semantics),
    review: cloneObject(canonical.review),
    provenance: cloneObject(canonical.provenance),
    assumptions: [...canonical.assumptions],
    details: canonical.details.map(mapDetail),
    summary: cloneSummary(canonical.summary)
  }
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

function readCanonicalResult(snapshot: unknown): FactoryPowerCanonicalResult | null {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return null
  const snapshotObject = snapshot as Record<string, unknown>
  if (isObject(snapshotObject.calculator)) {
    return snapshotObject as unknown as FactoryPowerCanonicalResult
  }
  if (isObject(snapshotObject.result) && isObject(snapshotObject.result.calculator)) {
    return snapshotObject.result as unknown as FactoryPowerCanonicalResult
  }
  return null
}

function isValidCanonicalResult(value: FactoryPowerCanonicalResult): boolean {
  return (
    value.schema_version === FACTORY_POWER_CALCULATOR_VERSION
    && value.result_kind === 'factory_power_canonical_result'
    && value.success === true
    && value.calculator?.id === FACTORY_POWER_CALCULATOR_ID
    && value.calculator?.version === FACTORY_POWER_CALCULATOR_VERSION
    && value.calculator?.identity === FACTORY_POWER_CALCULATOR_IDENTITY
    && isObject(value.input_authority)
    && typeof value.factory_area_band === 'string'
    && isObject(value.unit_semantics)
    && value.unit_semantics.power_unit === 'kW'
    && value.unit_semantics.not_energy === true
    && isObject(value.provenance)
    && Array.isArray(value.assumptions)
    && value.assumptions.every((item) => typeof item === 'string')
    && isObject(value.review)
    && value.review.requires_review === true
    && typeof value.review.status === 'string'
    && Array.isArray(value.details)
    && value.details.every(isValidDetail)
    && isObject(value.summary)
    && SUMMARY_FIELDS.every((field) => typeof value.summary[field] === 'string')
  )
}

function isValidPresentation(value: FactoryPowerPresentation): boolean {
  return (
    value.schema_version === FACTORY_POWER_CALCULATOR_VERSION
    && value.source_calculator_id === FACTORY_POWER_CALCULATOR_ID
    && value.source_calculator_version === FACTORY_POWER_CALCULATOR_VERSION
    && value.source_calculator_identity === FACTORY_POWER_CALCULATOR_IDENTITY
    && typeof value.canonical_result_hash === 'string'
    && value.canonical_result_hash.startsWith('sha256:')
    && typeof value.factory_area_band === 'string'
    && isObject(value.unit_semantics)
    && isObject(value.review)
    && value.review.requires_review === true
    && isObject(value.provenance)
    && Array.isArray(value.assumptions)
    && value.assumptions.every((item) => typeof item === 'string')
    && Array.isArray(value.details)
    && value.details.every(isValidDetail)
    && isObject(value.summary)
    && SUMMARY_FIELDS.every((field) => typeof value.summary[field] === 'string')
  )
}

function isValidDetail(value: FactoryPowerCanonicalDetail): boolean {
  return (
    isObject(value)
    && DETAIL_FIELDS.every((field) => field in value)
    && typeof value.equipment_or_zone === 'string'
    && typeof value.basis === 'string'
    && typeof value.configured_quantity === 'number'
    && Number.isInteger(value.configured_quantity)
    && typeof value.unit_power_kw === 'string'
    && typeof value.installed_power_kw === 'string'
    && typeof value.pool === 'string'
    && typeof value.simultaneity_factor === 'string'
    && typeof value.coincident_power_kw === 'string'
  )
}

function mapDetail(detail: FactoryPowerCanonicalDetail): FactoryPowerCanonicalDetail {
  return {
    equipment_or_zone: detail.equipment_or_zone,
    basis: detail.basis,
    configured_quantity: detail.configured_quantity,
    unit_power_kw: detail.unit_power_kw,
    installed_power_kw: detail.installed_power_kw,
    pool: detail.pool,
    simultaneity_factor: detail.simultaneity_factor,
    coincident_power_kw: detail.coincident_power_kw,
    display_label: DETAIL_LABELS[detail.equipment_or_zone] ?? detail.equipment_or_zone,
    pool_label: POOL_LABELS[detail.pool] ?? detail.pool
  }
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
    details: value.details.map(mapDetail),
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

function readCanonicalHash(
  record: CalculationRunRecord,
  canonical: FactoryPowerCanonicalResult
): string | null {
  const fromPayload = (canonical as unknown as Record<string, unknown>).canonical_result_hash
  if (typeof fromPayload === 'string' && fromPayload.startsWith('sha256:')) {
    return fromPayload
  }
  if (typeof record.result_hash !== 'string' || !record.result_hash) return null
  return record.result_hash.startsWith('sha256:')
    ? record.result_hash
    : `sha256:${record.result_hash}`
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
