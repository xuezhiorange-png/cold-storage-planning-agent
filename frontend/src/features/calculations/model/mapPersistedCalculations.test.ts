import { describe, expect, it } from 'vitest'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import {
  mapPersistedCalculationsToPlanningResponse,
  readPersistedFormulas,
  readPersistedResultPayload
} from './mapPersistedCalculations'

function zoneRecord(
  zones: Array<Record<string, unknown>>,
  resultExtras: Record<string, unknown> = {},
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
      result: { zones, ...resultExtras }
    },
    requires_review: false
  }
}

function powerConfigurationRecord(
  equipmentRows: Array<Record<string, unknown>>,
  totalPowerKw = 1350,
  id = 'pwr-1'
): CalculationRunRecord {
  return {
    id,
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: 'power_configuration',
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: 'power_configuration',
      calculator_version: '1.0.0',
      input: {},
      result: {
        equipment_rows: equipmentRows,
        summary_rows: [{ name: '合计', basis: '', total_power_kw: totalPowerKw }],
        items: [],
        total_installed_power_kw: totalPowerKw,
        total_estimated_demand_kw: totalPowerKw,
        requires_review: true
      }
    },
    requires_review: true
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

  it('maps persisted power_configuration equipment rows', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      zoneRecord([{
        zone_name: '成品冷藏',
        temperature_band: '冷藏',
        position_count: 40,
        required_area_m2: 300,
        daily_throughput_kg: 0,
        design_storage_mass_kg: 0
      }]),
      investmentRecord([{ item_name: '土建', amount_cny: 600_000 }]),
      powerConfigurationRecord([
        {
          sequence: 1,
          name: '冷风机',
          area: '成品库',
          quantity: 3,
          defrost_power_kw: null,
          defrost_total_power_kw: null,
          running_power_kw: 2.5,
          total_power_kw: 7.5
        }
      ])
    ])

    expect(mapped).not.toBeNull()
    expect(mapped!.power_configuration.equipment_rows.length).toBe(1)
    expect(mapped!.power_configuration.equipment_rows[0].name).toBe('冷风机')
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
      }], {}, 'zone-old'),
      investmentRecord([{ item_name: '旧分项', amount_cny: 100_000 }], 1000, 'inv-old', 500_000),
      zoneRecord([{
        zone_name: '新区域',
        temperature_band: '冷藏',
        position_count: 40,
        required_area_m2: 300,
        daily_throughput_kg: 0,
        design_storage_mass_kg: 0
      }], {}, 'zone-new'),
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

  it('passes through P2 zone layout and scheme fields', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      zoneRecord([
        {
          zone_name: '一级预冷间',
          temperature_band: '8~10℃',
          daily_throughput_kg_day: 20000,
          design_storage_mass_kg: 0,
          position_count: 18,
          required_area_m2: 270,
          zone_code: 'primary_precool',
          n_need: 16,
          reporting_scheme_id: '6_position',
          schemes: [
            {
              scheme_id: '6_position',
              room_count: 3,
              position_count: 18,
              required_area_m2: 270
            },
            {
              scheme_id: '8_position',
              room_count: 2,
              position_count: 16,
              required_area_m2: 272
            }
          ]
        },
        {
          zone_name: '出货通道',
          temperature_band: '1~3℃',
          design_storage_mass_kg: 0,
          position_count: 2,
          required_area_m2: 110,
          zone_code: 'shipping_channel',
          pallet_count: 42,
          truck_count: 3,
          platform_count: 2
        }
      ], {
        total_area_m2: 900,
        total_area_m2_8_position_scheme: 950
      })
    ])

    expect(mapped).not.toBeNull()
    const precool = mapped!.zone_plan.result.zones[0]
    expect(precool.zone_code).toBe('primary_precool')
    expect(precool.n_need).toBe(16)
    expect(precool.reporting_scheme_id).toBe('6_position')
    expect(precool.schemes).toEqual([
      {
        scheme_id: '6_position',
        room_count: 3,
        position_count: 18,
        required_area_m2: 270
      },
      {
        scheme_id: '8_position',
        room_count: 2,
        position_count: 16,
        required_area_m2: 272
      }
    ])
    expect(precool.daily_throughput_kg_day).toBe(20000)

    const shipping = mapped!.zone_plan.result.zones[1]
    expect(shipping.pallet_count).toBe(42)
    expect(shipping.truck_count).toBe(3)
    expect(shipping.platform_count).toBe(2)

    expect(mapped!.summary.total_area_m2).toBe(900)
    expect(mapped!.summary.total_area_m2_8_position_scheme).toBe(950)
  })

  it('keeps absent optional zone fields undefined instead of fabricating zero', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      zoneRecord([{
        zone_name: '成品间',
        temperature_band: '1~3℃',
        position_count: 20,
        required_area_m2: 300,
        daily_throughput_kg: 0,
        design_storage_mass_kg: 0
      }])
    ])

    expect(mapped).not.toBeNull()
    const zone = mapped!.zone_plan.result.zones[0]
    expect(zone.n_need).toBeUndefined()
    expect(zone.n_actual).toBeUndefined()
    expect(zone.unused_cells).toBeUndefined()
    expect(zone.pallet_count).toBeUndefined()
    expect(zone.truck_count).toBeUndefined()
    expect(zone.platform_count).toBeUndefined()
    expect(zone.schemes).toBeUndefined()
    expect(zone.reporting_scheme_id).toBeUndefined()
    expect(mapped!.summary.total_area_m2_8_position_scheme).toBeUndefined()
  })

  it('dual-reads zone snapshot when zones are nested under result.result', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      {
        id: 'zone-nested',
        project_id: 'proj-1',
        project_version_id: 'ver-1',
        calculator_name: 'cold_room_zone_plan',
        calculator_version: '1.0.0',
        result_snapshot: {
          success: true,
          calculator_name: 'cold_room_zone_plan',
          calculator_version: '1.0.0',
          input: {},
          result: {
            result: {
              zones: [{
                zone_name: '嵌套区域',
                temperature_band: '冷藏',
                daily_throughput_kg: 0,
                design_storage_mass_kg: 0,
                position_count: 12,
                required_area_m2: 120
              }],
              total_area_m2: 120
            }
          }
        },
        requires_review: false
      }
    ])

    expect(mapped).not.toBeNull()
    expect(mapped!.zone_plan.result.zones[0].zone_name).toBe('嵌套区域')
    expect(mapped!.summary.total_area_m2).toBe(120)
  })

  it('passes through packed layout fields when present', () => {
    const mapped = mapPersistedCalculationsToPlanningResponse([
      zoneRecord([{
        zone_name: '成品间',
        temperature_band: '1~3℃',
        position_count: 28,
        required_area_m2: 400,
        daily_throughput_kg: 0,
        design_storage_mass_kg: 5000,
        n_need: 24,
        n_long: 7,
        n_short: 4,
        n_actual: 28,
        unused_cells: 4,
        aisle_layout: 'three_side_3m',
        layout: { n_long: 7, n_short: 4, aspect_ratio: 1.75 }
      }])
    ])

    expect(mapped).not.toBeNull()
    const zone = mapped!.zone_plan.result.zones[0]
    expect(zone.n_need).toBe(24)
    expect(zone.n_long).toBe(7)
    expect(zone.n_short).toBe(4)
    expect(zone.n_actual).toBe(28)
    expect(zone.unused_cells).toBe(4)
    expect(zone.aisle_layout).toBe('three_side_3m')
    expect(zone.layout).toEqual({ n_long: 7, n_short: 4, aspect_ratio: 1.75 })
  })

  it('reads formulas from record.formulas when present', () => {
    const record: CalculationRunRecord = {
      id: 'calc-cooling',
      project_id: 'proj-1',
      project_version_id: 'ver-1',
      calculator_name: 'cooling_load',
      calculator_version: '1.0.0',
      result_snapshot: {
        success: true,
        calculator_name: 'cooling_load',
        calculator_version: '1.0.0',
        input: {},
        result: { total_cooling_load_kw: '10' }
      },
      formulas: [
        {
          formula_id: 'F1',
          formula_version: '1.0',
          expression: 'Q = m * cp * dT',
          description: 'Sensible heat'
        }
      ],
      requires_review: false
    }

    expect(readPersistedFormulas(record)).toEqual([
      {
        formula_id: 'F1',
        formula_version: '1.0',
        expression: 'Q = m * cp * dT',
        description: 'Sensible heat'
      }
    ])
    expect(readPersistedResultPayload(record)?.total_cooling_load_kw).toBe('10')
  })
})
