import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import type {
  EquipmentPowerRowContract,
  PlanningRunResponse,
  PowerItemContract,
  PowerSummaryRowContract
} from '../../../api/contracts/planning'

const ZONE_CALCULATOR = 'cold_room_zone_plan'
const COOLING_LOAD_CALCULATOR = 'cooling_load'
const EQUIPMENT_CALCULATOR = 'equipment'
const POWER_CALCULATOR = 'installed_power'
const INVESTMENT_CALCULATOR = 'investment_estimate'
const POWER_CONFIGURATION_CALCULATOR = 'power_configuration'

function asNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return 0
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
  const zones = record?.result_snapshot?.result?.zones
  return Array.isArray(zones) ? zones.filter((zone) => zone && typeof zone === 'object') as Array<Record<string, unknown>> : []
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
  powerRecord: CalculationRunRecord | undefined,
  requiresReview: boolean
): PlanningRunResponse['power_configuration'] {
  const persisted = record?.result_snapshot?.result ?? {}
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

  const investmentInput = investmentRecord?.result_snapshot?.input ?? {}
  const powerResult = powerRecord?.result_snapshot?.result ?? {}
  const totalFromPowerTable = asNumber(persisted.total_installed_power_kw)
  const totalFromInvestment = asNumber(investmentInput.total_power_kw)
  const totalFromInstalledPower = asNumber(
    powerResult.total_installed_power_kw_e ?? powerResult.total_installed_power_kw
  )
  const totalInstalled = totalFromPowerTable > 0
    ? totalFromPowerTable
    : totalFromInvestment > 0
      ? totalFromInvestment
      : totalFromInstalledPower

  const totalDemand = asNumber(
    persisted.total_estimated_demand_kw ?? powerResult.estimated_peak_demand_kw_e ?? totalInstalled
  )

  return {
    equipment_rows: equipmentRows,
    summary_rows: summaryRows,
    items,
    total_installed_power_kw: totalInstalled,
    total_estimated_demand_kw: totalDemand,
    requires_review: Boolean(persisted.requires_review ?? record?.requires_review ?? requiresReview)
  }
}

/**
 * Map persisted calculation runs into the planning response view shape used by workbench pages.
 * Reads persisted five-stage runs only — no transient demo planning-run fallback.
 */
export function mapPersistedCalculationsToPlanningResponse(
  records: CalculationRunRecord[]
): PlanningRunResponse | null {
  const byName = latestByCalculatorName(records)
  const zoneRecord = byName[ZONE_CALCULATOR]
  if (!zoneRecord) return null

  const investmentRecord = byName[INVESTMENT_CALCULATOR]
  const powerConfigurationRecord = byName[POWER_CONFIGURATION_CALCULATOR]
  const powerRecord = byName[POWER_CALCULATOR]
  const zones = zoneRows(zoneRecord)
  if (zones.length === 0) return null

  const totalAreaM2 = zones.reduce((sum, zone) => sum + asNumber(zone.required_area_m2), 0)
  const totalPositionCount = zones.reduce((sum, zone) => sum + asNumber(zone.position_count), 0)
  const investmentResult = investmentRecord?.result_snapshot?.result ?? {}
  const totalInvestmentCny = asNumber(investmentResult.total_investment_cny)
  const powerConfiguration = powerConfigurationFromRecord(
    powerConfigurationRecord,
    investmentRecord,
    powerRecord,
    Boolean(zoneRecord.requires_review) || Boolean(investmentRecord?.requires_review)
  )

  const requiresReview =
    Boolean(zoneRecord.requires_review)
    || Boolean(investmentRecord?.requires_review)
    || Boolean(powerConfigurationRecord?.requires_review)
    || Boolean(byName[COOLING_LOAD_CALCULATOR]?.requires_review)
    || Boolean(byName[EQUIPMENT_CALCULATOR]?.requires_review)
    || Boolean(powerRecord?.requires_review)

  return {
    success: Boolean(zoneRecord.result_snapshot?.success),
    summary: {
      total_area_m2: totalAreaM2,
      total_position_count: totalPositionCount,
      total_investment_cny: totalInvestmentCny,
      total_power_kw: powerConfiguration.total_installed_power_kw,
      requires_review: requiresReview
    },
    zone_plan: {
      result: {
        zones: zones.map((zone) => ({
          zone_name: String(zone.zone_name ?? ''),
          temperature_band: String(zone.temperature_band ?? ''),
          daily_throughput_kg: asNumber(zone.daily_throughput_kg),
          design_storage_mass_kg: asNumber(zone.design_storage_mass_kg),
          position_count: asNumber(zone.position_count),
          required_area_m2: asNumber(zone.required_area_m2)
        }))
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
