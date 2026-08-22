import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import type { PlanningRunResponse } from '../../../api/contracts/planning'

const ZONE_CALCULATOR = 'cold_room_zone_plan'
const INVESTMENT_CALCULATOR = 'investment_estimate'

function asNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return 0
}

function latestByCalculatorName(records: CalculationRunRecord[]): Record<string, CalculationRunRecord> {
  const latest: Record<string, CalculationRunRecord> = {}
  for (const record of records) {
    const name = record.calculator_name
    if (name && !latest[name]) {
      latest[name] = record
    }
  }
  return latest
}

function zoneRows(record: CalculationRunRecord | undefined): Array<Record<string, unknown>> {
  const zones = record?.result_snapshot?.result?.zones
  return Array.isArray(zones) ? zones.filter((zone) => zone && typeof zone === 'object') as Array<Record<string, unknown>> : []
}

/**
 * Map persisted calculation runs into the planning response view shape used by workbench pages.
 * Summaries aggregate persisted zone outputs only — no frontend engineering formulas.
 */
export function mapPersistedCalculationsToPlanningResponse(
  records: CalculationRunRecord[]
): PlanningRunResponse | null {
  const byName = latestByCalculatorName(records)
  const zoneRecord = byName[ZONE_CALCULATOR]
  if (!zoneRecord) return null

  const investmentRecord = byName[INVESTMENT_CALCULATOR]
  const zones = zoneRows(zoneRecord)
  if (zones.length === 0) return null

  const totalAreaM2 = zones.reduce((sum, zone) => sum + asNumber(zone.required_area_m2), 0)
  const totalPositionCount = zones.reduce((sum, zone) => sum + asNumber(zone.position_count), 0)
  const investmentResult = investmentRecord?.result_snapshot?.result ?? {}
  const investmentInput = investmentRecord?.result_snapshot?.input ?? {}
  const totalInvestmentCny = asNumber(investmentResult.total_investment_cny)
  const totalPowerKw = asNumber(investmentInput.total_power_kw)

  const requiresReview =
    Boolean(zoneRecord.requires_review) || Boolean(investmentRecord?.requires_review)

  return {
    success: Boolean(zoneRecord.result_snapshot?.success),
    summary: {
      total_area_m2: totalAreaM2,
      total_position_count: totalPositionCount,
      total_investment_cny: totalInvestmentCny,
      total_power_kw: totalPowerKw,
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
    power_configuration: {
      equipment_rows: [],
      summary_rows:
        totalPowerKw > 0
          ? [{
              name: '装机总功率',
              basis: '持久化投资测算输入',
              total_power_kw: totalPowerKw
            }]
          : [],
      items: [],
      total_installed_power_kw: totalPowerKw,
      total_estimated_demand_kw: 0,
      requires_review: requiresReview
    }
  }
}
