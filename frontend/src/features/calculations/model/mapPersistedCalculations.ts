import type {
  CalculationRunRecord,
  PersistedFormulaEntry
} from '../../../api/contracts/calculations'
import type {
  EquipmentPowerRowContract,
  PlanningRunResponse,
  PowerItemContract,
  PowerSummaryRowContract,
  ZoneLayoutContract,
  ZoneResultContract,
  ZoneSchemeContract
} from '../../../api/contracts/planning'

const ZONE_CALCULATOR = 'cold_room_zone_plan'
const INVESTMENT_CALCULATOR = 'investment_estimate'
const POWER_CONFIGURATION_CALCULATOR = 'power_configuration'

const EMPTY_STAGE_COPY = '本阶段尚无持久化结果'

/**
 * Dual-read persisted snapshot payload (V0.9 P6): unwrap `.result` when present.
 */
export function readPersistedResultPayload(
  record: CalculationRunRecord | null | undefined
): Record<string, unknown> | null {
  if (!record?.result_snapshot || typeof record.result_snapshot !== 'object') {
    return null
  }
  return readResultPayloadFromSnapshot(record.result_snapshot)
}

export function readResultPayloadFromSnapshot(snapshot: unknown): Record<string, unknown> {
  if (!snapshot || typeof snapshot !== 'object') return {}
  const snap = snapshot as Record<string, unknown>
  const result = snap.result
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const resultDict = result as Record<string, unknown>
    const nested = resultDict.result
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      return nested as Record<string, unknown>
    }
    return resultDict
  }
  return snap
}

export function readPersistedFormulas(
  record: CalculationRunRecord | null | undefined
): PersistedFormulaEntry[] {
  const fromRecord = record?.formulas
  if (Array.isArray(fromRecord) && fromRecord.length > 0) {
    return fromRecord.filter((entry) => entry && typeof entry === 'object')
  }
  const snapshot = record?.result_snapshot
  if (snapshot && typeof snapshot === 'object') {
    const formulas = (snapshot as Record<string, unknown>).formulas
    if (Array.isArray(formulas) && formulas.length > 0) {
      return formulas.filter((entry) => entry && typeof entry === 'object') as PersistedFormulaEntry[]
    }
  }
  return []
}

export function readPersistedAssumptions(
  record: CalculationRunRecord | null | undefined
): string[] {
  const fromRecord = record?.assumptions
  if (Array.isArray(fromRecord) && fromRecord.length > 0) {
    return fromRecord.filter((item): item is string => typeof item === 'string')
  }
  const payload = readPersistedResultPayload(record)
  const assumptions = payload?.assumptions
  if (Array.isArray(assumptions)) {
    return assumptions.filter((item): item is string => typeof item === 'string')
  }
  return []
}

export function readPersistedWarnings(
  record: CalculationRunRecord | null | undefined
): string[] {
  const fromRecord = record?.warnings
  if (Array.isArray(fromRecord) && fromRecord.length > 0) {
    return fromRecord.map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object' && 'message' in item) {
        return String((item as Record<string, unknown>).message ?? item)
      }
      return String(item)
    })
  }
  const payload = readPersistedResultPayload(record)
  const warnings = payload?.warnings
  if (Array.isArray(warnings)) {
    return warnings.map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object' && 'message' in item) {
        return String((item as Record<string, unknown>).message ?? item)
      }
      return String(item)
    })
  }
  return []
}

export function formatPersistedNumber(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(2)
    }
    return value
  }
  return '—'
}

export function formatPersistedWan(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number(value)
        : NaN
  if (!Number.isFinite(parsed)) return '—'
  return `${(parsed / 10000).toFixed(2)} 万元`
}

export function persistedObjectRows(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return []
  return value.filter((row) => row && typeof row === 'object') as Array<Record<string, unknown>>
}

export { EMPTY_STAGE_COPY }

function asNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return 0
}

function asOptionalNumber(value: unknown): number | undefined {
  if (value === null || value === undefined) return undefined
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function asOptionalInt(value: unknown): number | undefined {
  const parsed = asOptionalNumber(value)
  return parsed === undefined ? undefined : parsed
}

function asOptionalString(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined
  const text = String(value).trim()
  return text ? text : undefined
}

function snapshotInput(snapshot: unknown): Record<string, unknown> {
  if (!snapshot || typeof snapshot !== 'object') return {}
  const input = (snapshot as Record<string, unknown>).input
  return input && typeof input === 'object' && !Array.isArray(input)
    ? (input as Record<string, unknown>)
    : {}
}

/**
 * API returns calculation runs in created_at ascending order; last entry per name wins.
 */
function latestByCalculatorName(records: CalculationRunRecord[]): Record<string, CalculationRunRecord> {
  const latest: Record<string, CalculationRunRecord> = {}
  for (const record of records) {
    const name = record.calculator_name
    if (name) {
      latest[name] = record
    }
  }
  return latest
}

function zoneRows(record: CalculationRunRecord | undefined): Array<Record<string, unknown>> {
  const payload = readResultPayloadFromSnapshot(record?.result_snapshot)
  const zones = payload.zones
  return Array.isArray(zones)
    ? zones.filter((zone) => zone && typeof zone === 'object') as Array<Record<string, unknown>>
    : []
}

function mapZoneScheme(row: Record<string, unknown>): ZoneSchemeContract {
  const scheme: ZoneSchemeContract = {
    scheme_id: String(row.scheme_id ?? ''),
    room_count: asNumber(row.room_count),
    position_count: asNumber(row.position_count),
    required_area_m2: asNumber(row.required_area_m2)
  }
  const positionsPerRoom = asOptionalInt(row.positions_per_room)
  if (positionsPerRoom !== undefined) {
    scheme.positions_per_room = positionsPerRoom
  }
  return scheme
}

function mapZoneLayout(row: Record<string, unknown>): ZoneLayoutContract {
  const layout: ZoneLayoutContract = {}
  const nLong = asOptionalInt(row.n_long)
  const nShort = asOptionalInt(row.n_short)
  const aspectRatio = asOptionalNumber(row.aspect_ratio)
  if (nLong !== undefined) layout.n_long = nLong
  if (nShort !== undefined) layout.n_short = nShort
  if (aspectRatio !== undefined) layout.aspect_ratio = aspectRatio
  return layout
}

function mapZone(zone: Record<string, unknown>): ZoneResultContract {
  const mapped: ZoneResultContract = {
    zone_name: String(zone.zone_name ?? ''),
    temperature_band: String(zone.temperature_band ?? ''),
    daily_throughput_kg: asNumber(zone.daily_throughput_kg),
    design_storage_mass_kg: asNumber(zone.design_storage_mass_kg),
    position_count: asNumber(zone.position_count),
    required_area_m2: asNumber(zone.required_area_m2)
  }

  const dailyThroughputKgDay = asOptionalNumber(zone.daily_throughput_kg_day)
  if (dailyThroughputKgDay !== undefined) {
    mapped.daily_throughput_kg_day = dailyThroughputKgDay
  }

  const zoneCode = asOptionalString(zone.zone_code)
  if (zoneCode) mapped.zone_code = zoneCode

  const nNeed = asOptionalInt(zone.n_need)
  if (nNeed !== undefined) mapped.n_need = nNeed

  const nLong = asOptionalInt(zone.n_long)
  if (nLong !== undefined) mapped.n_long = nLong

  const nShort = asOptionalInt(zone.n_short)
  if (nShort !== undefined) mapped.n_short = nShort

  const nActual = asOptionalInt(zone.n_actual)
  if (nActual !== undefined) mapped.n_actual = nActual

  const unusedCells = asOptionalInt(zone.unused_cells)
  if (unusedCells !== undefined) mapped.unused_cells = unusedCells

  const aisleLayout = asOptionalString(zone.aisle_layout)
  if (aisleLayout) mapped.aisle_layout = aisleLayout

  const reportingSchemeId = asOptionalString(zone.reporting_scheme_id)
  if (reportingSchemeId) mapped.reporting_scheme_id = reportingSchemeId

  if (Array.isArray(zone.schemes) && zone.schemes.length > 0) {
    mapped.schemes = zone.schemes.map((scheme) =>
      mapZoneScheme(scheme as Record<string, unknown>)
    )
  }

  if (zone.layout && typeof zone.layout === 'object') {
    mapped.layout = mapZoneLayout(zone.layout as Record<string, unknown>)
  }

  const palletCount = asOptionalInt(zone.pallet_count)
  if (palletCount !== undefined) mapped.pallet_count = palletCount

  const truckCount = asOptionalInt(zone.truck_count)
  if (truckCount !== undefined) mapped.truck_count = truckCount

  const platformCount = asOptionalInt(zone.platform_count)
  if (platformCount !== undefined) mapped.platform_count = platformCount

  return mapped
}

function mapEquipmentRow(row: Record<string, unknown>, index: number): EquipmentPowerRowContract {
  return {
    sequence: asNumber(row.sequence) || index + 1,
    name: String(row.name ?? ''),
    area: String(row.area ?? ''),
    quantity: asNumber(row.quantity),
    defrost_power_kw: row.defrost_power_kw === null || row.defrost_power_kw === undefined
      ? null
      : asNumber(row.defrost_power_kw),
    defrost_total_power_kw: row.defrost_total_power_kw === null || row.defrost_total_power_kw === undefined
      ? null
      : asNumber(row.defrost_total_power_kw),
    running_power_kw: asNumber(row.running_power_kw),
    total_power_kw: asNumber(row.total_power_kw)
  }
}

function mapSummaryRow(row: Record<string, unknown>): PowerSummaryRowContract {
  return {
    name: String(row.name ?? ''),
    basis: String(row.basis ?? ''),
    total_power_kw: asNumber(row.total_power_kw)
  }
}

function mapPowerItem(row: Record<string, unknown>): PowerItemContract {
  return {
    category: String(row.category ?? ''),
    installed_power_kw: asNumber(row.installed_power_kw),
    demand_factor: asNumber(row.demand_factor),
    estimated_demand_kw: asNumber(row.estimated_demand_kw)
  }
}

function powerConfigurationFromRecord(
  record: CalculationRunRecord | undefined,
  investmentRecord: CalculationRunRecord | undefined,
  requiresReview: boolean
): PlanningRunResponse['power_configuration'] {
  const persisted = readResultPayloadFromSnapshot(record?.result_snapshot)
  const equipmentRows = Array.isArray(persisted.equipment_rows)
    ? persisted.equipment_rows.map((row, idx) =>
        mapEquipmentRow(row as Record<string, unknown>, idx)
      )
    : []
  const summaryRows = Array.isArray(persisted.summary_rows)
    ? persisted.summary_rows.map((row) => mapSummaryRow(row as Record<string, unknown>))
    : []
  const items = Array.isArray(persisted.items)
    ? persisted.items.map((row) => mapPowerItem(row as Record<string, unknown>))
    : []

  const investmentInput = snapshotInput(investmentRecord?.result_snapshot)
  const totalFromPowerTable = asNumber(persisted.total_installed_power_kw)
  const totalFromInvestment = asNumber(investmentInput.total_power_kw)
  const totalInstalled = totalFromPowerTable > 0 ? totalFromPowerTable : totalFromInvestment
  const totalDemand = asNumber(persisted.total_estimated_demand_kw)

  return {
    equipment_rows: equipmentRows,
    summary_rows: summaryRows,
    items,
    total_installed_power_kw: totalInstalled,
    total_estimated_demand_kw: totalDemand > 0 ? totalDemand : totalInstalled,
    requires_review: Boolean(persisted.requires_review ?? record?.requires_review ?? requiresReview)
  }
}

/**
 * Map persisted calculation runs into the planning response view shape used by workbench pages.
 * Reads persisted planning-helper outputs only — no transient demo planning-run fallback.
 */
export function mapPersistedCalculationsToPlanningResponse(
  records: CalculationRunRecord[]
): PlanningRunResponse | null {
  const byName = latestByCalculatorName(records)
  const zoneRecord = byName[ZONE_CALCULATOR]
  if (!zoneRecord) return null

  const investmentRecord = byName[INVESTMENT_CALCULATOR]
  const powerConfigurationRecord = byName[POWER_CONFIGURATION_CALCULATOR]
  const zones = zoneRows(zoneRecord)
  if (zones.length === 0) return null

  const zoneResult = readResultPayloadFromSnapshot(zoneRecord.result_snapshot)
  const persistedTotalArea = asOptionalNumber(zoneResult.total_area_m2)
  const totalAreaM2 =
    persistedTotalArea !== undefined
      ? persistedTotalArea
      : zones.reduce((sum, zone) => sum + asNumber(zone.required_area_m2), 0)
  const totalPositionCount = zones.reduce((sum, zone) => sum + asNumber(zone.position_count), 0)
  const totalArea8PositionScheme = asOptionalNumber(zoneResult.total_area_m2_8_position_scheme)
  const investmentResult = readResultPayloadFromSnapshot(investmentRecord?.result_snapshot)
  const totalInvestmentCny = asNumber(investmentResult.total_investment_cny)
  const powerConfiguration = powerConfigurationFromRecord(
    powerConfigurationRecord,
    investmentRecord,
    Boolean(zoneRecord.requires_review) || Boolean(investmentRecord?.requires_review)
  )

  const requiresReview =
    Boolean(zoneRecord.requires_review)
    || Boolean(investmentRecord?.requires_review)
    || Boolean(powerConfigurationRecord?.requires_review)

  const summary: PlanningRunResponse['summary'] = {
    total_area_m2: totalAreaM2,
    total_position_count: totalPositionCount,
    total_investment_cny: totalInvestmentCny,
    total_power_kw: powerConfiguration.total_installed_power_kw,
    requires_review: requiresReview
  }
  if (totalArea8PositionScheme !== undefined) {
    summary.total_area_m2_8_position_scheme = totalArea8PositionScheme
  }

  const zoneSnapshot = zoneRecord.result_snapshot
  const snapshotSuccess =
    zoneSnapshot && typeof zoneSnapshot === 'object'
      ? (zoneSnapshot as Record<string, unknown>).success
      : undefined

  return {
    success: Boolean(snapshotSuccess),
    summary,
    zone_plan: {
      result: {
        zones: zones.map((zone) => mapZone(zone))
      }
    },
    investment_estimate: {
      result: {
        items: Array.isArray(investmentResult.items)
          ? investmentResult.items.map((item) => {
              const row = item as Record<string, unknown>
              return {
                item_name: String(row.item_name ?? ''),
                amount_cny: asNumber(row.amount_cny)
              }
            })
          : []
      }
    },
    power_configuration: powerConfiguration
  }
}
