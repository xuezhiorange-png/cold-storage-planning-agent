import { describe, expect, it } from 'vitest'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import { mapPersistedCalculationsToPlanningResponse } from './mapPersistedCalculations'

function zoneRecord(
  zones: Array<Record<string, unknown>>,
  id = 'zone-1'
): CalculationRunRecord {
  return {
    id,
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: 'cold_room_zone_plan',
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: 'cold_room_zone_plan',
      calculator_version: '1.0.0',
      input: {},
      result: { zones }
    },
    requires_review: false
  }
}

function investmentRecord(
  items: Array<{ item_name: string; amount_cny: number }>,
  totalPowerKw = 1350,
  id = 'inv-1',
  totalInvestmentCny = 1_200_000
): CalculationRunRecord {
  return {
    id,
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: 'investment_estimate',
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: 'investment_estimate',
      calculator_version: '1.0.0',
      input: {
        total_area_m2: 850,
        total_power_kw: totalPowerKw,
        position_count: 300
      },
      result: {
        total_investment_cny: totalInvestmentCny,
        items
      }
    },
    requires_review: true
  }
}

describe('mapPersistedCalculationsToPlanningResponse', () => {
  it('maps zone and investment runs into planning display shape', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      zoneRecord([
        {
          zone_name: '原料暂存',
          temperature_band: '常温',
          daily_throughput_kg: 12000,
          design_storage_mass_kg: 24000,
          position_count: 80,
          required_area_m2: 200
        },
        {
          zone_name: '成品冷藏',
          temperature_band: '冷藏',
          daily_throughput_kg: 15000,
          design_storage_mass_kg: 37500,
          position_count: 120,
          required_area_m2: 450
        }
      ]),
      investmentRecord([
        { item_name: '土建', amount_cny: 600_000 },
        { item_name: '设备', amount_cny: 400_000 }
      ])
    ])

    expect(mapped).not.toBeNull()
    expect(mapped!.summary.total_area_m2).toBe(650)
    expect(mapped!.summary.total_position_count).toBe(200)
    expect(mapped!.summary.total_investment_cny).toBe(1_200_000)
    expect(mapped!.summary.total_power_kw).toBe(1350)
    expect(mapped!.zone_plan.result.zones.length).toBe(2)
    expect(mapped!.investment_estimate.result.items.length).toBe(2)
    expect(mapped!.power_configuration.total_installed_power_kw).toBe(1350)
  })

  it('returns null when zone plan is missing', () => {
    expect(mapPersistedCalculationsToPlanningResponse([
      investmentRecord([{ item_name: '土建', amount_cny: 100 }])
    ])).toBeNull()
  })

  it('uses the newest run per calculator_name when API lists runs in created_at ascending order', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      zoneRecord([{
        zone_name: '旧区域',
        temperature_band: '常温',
        position_count: 10,
        required_area_m2: 100,
        daily_throughput_kg: 0,
        design_storage_mass_kg: 0
      }], 'zone-old'),
      investmentRecord([{ item_name: '旧分项', amount_cny: 100_000 }], 1000, 'inv-old', 500_000),
      zoneRecord([{
        zone_name: '新区域',
        temperature_band: '冷藏',
        position_count: 40,
        required_area_m2: 300,
        daily_throughput_kg: 0,
        design_storage_mass_kg: 0
      }], 'zone-new'),
      investmentRecord([{ item_name: '新分项', amount_cny: 900_000 }], 2000, 'inv-new', 2_000_000)
    ])

    expect(mapped).not.toBeNull()
    expect(mapped!.summary.total_area_m2).toBe(300)
    expect(mapped!.summary.total_position_count).toBe(40)
    expect(mapped!.summary.total_investment_cny).toBe(2_000_000)
    expect(mapped!.summary.total_power_kw).toBe(2000)
    expect(mapped!.zone_plan.result.zones).toEqual([{
      zone_name: '新区域',
      temperature_band: '冷藏',
      daily_throughput_kg: 0,
      design_storage_mass_kg: 0,
      position_count: 40,
      required_area_m2: 300
    }])
    expect(mapped!.investment_estimate.result.items).toEqual([
      { item_name: '新分项', amount_cny: 900_000 }
    ])
  })
})
