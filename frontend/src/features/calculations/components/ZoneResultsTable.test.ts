import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { ZoneResultContract } from '../../../api/contracts/planning'
import ZoneResultsTable from './ZoneResultsTable.vue'

function createZones(): ZoneResultContract[] {
  return [
    {
      zone_name: '一级预冷间',
      temperature_band: '8~10℃',
      daily_throughput_kg_day: 25000,
      design_storage_mass_kg: 0,
      position_count: 24,
      required_area_m2: 134.4
    },
    {
      zone_name: '成品间',
      temperature_band: '1~3℃',
      daily_throughput_kg: 25000,
      design_storage_mass_kg: 62500,
      position_count: 157,
      required_area_m2: 293.9
    },
    {
      zone_name: '包材库',
      temperature_band: '常温',
      daily_throughput_kg: 25000,
      design_storage_mass_kg: 0,
      position_count: 90,
      required_area_m2: 210.6
    }
  ]
}

describe('ZoneResultsTable', () => {
  it('renders zone rows from props', () => {
    const zones = createZones()
    const wrapper = mount(ZoneResultsTable, {
      props: { zones }
    })

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(3)
  })

  it('displays zone name and temperature band', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: { zones: createZones() }
    })

    expect(wrapper.text()).toContain('一级预冷间')
    expect(wrapper.text()).toContain('8~10℃')
    expect(wrapper.text()).toContain('成品间')
    expect(wrapper.text()).toContain('1~3℃')
  })

  it('displays throughput from daily_throughput_kg_day', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: 'Test',
            temperature_band: '常温',
            daily_throughput_kg_day: 30000,
            design_storage_mass_kg: 0,
            position_count: 0,
            required_area_m2: 100
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('30000 kg/day')
  })

  it('displays throughput from daily_throughput_kg as fallback', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: 'Test',
            temperature_band: '常温',
            daily_throughput_kg: 15000,
            design_storage_mass_kg: 0,
            position_count: 0,
            required_area_m2: 100
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('15000 kg/day')
  })

  it('shows dash when no throughput data', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: 'Test',
            temperature_band: '常温',
            design_storage_mass_kg: 0,
            position_count: 0,
            required_area_m2: 100
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('-')
  })

  it('shows "按周转配置" when storage mass is zero', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: 'Test',
            temperature_band: '常温',
            daily_throughput_kg: 10000,
            design_storage_mass_kg: 0,
            position_count: 0,
            required_area_m2: 100
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('按周转配置')
  })

  it('displays storage mass in tons when >= 1000 kg', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: 'Test',
            temperature_band: '常温',
            daily_throughput_kg: 10000,
            design_storage_mass_kg: 62500,
            position_count: 157,
            required_area_m2: 293.9
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('62.50 t')
  })

  it('displays area with m² suffix', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: { zones: createZones() }
    })

    expect(wrapper.text()).toContain('134.40 m²')
    expect(wrapper.text()).toContain('293.90 m²')
  })

  it('labels reporting columns as 6-position scheme', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: { zones: createZones() }
    })

    expect(wrapper.text()).toContain('板位 (6位汇报)')
    expect(wrapper.text()).toContain('面积 (6位汇报)')
  })

  it('shows both precooling schemes when schemes array is present', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: '一级预冷间',
            temperature_band: '8~10℃',
            design_storage_mass_kg: 0,
            position_count: 18,
            required_area_m2: 270,
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
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('6_position')
    expect(wrapper.text()).toContain('8_position')
    expect(wrapper.text()).toContain('间数 3')
    expect(wrapper.text()).toContain('间数 2')
    expect(wrapper.text()).toContain('270 m²')
    expect(wrapper.text()).toContain('272 m²')
    expect(wrapper.text()).toContain('6位汇报方案：6_position')
    expect(wrapper.text()).toContain('18')
    expect(wrapper.text()).not.toContain('16 m²')
  })

  it('shows need vs actual layout fields when n_need is present', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: '成品间',
            temperature_band: '1~3℃',
            design_storage_mass_kg: 5000,
            position_count: 28,
            required_area_m2: 400,
            zone_code: 'finished_goods_room',
            n_need: 24,
            n_actual: 28,
            unused_cells: 4,
            n_long: 7,
            n_short: 4,
            aisle_layout: 'three_side_3m'
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('finished_goods_room')
    expect(wrapper.text()).toContain('需求 24')
    expect(wrapper.text()).toContain('实际 28')
    expect(wrapper.text()).toContain('空余 4')
    expect(wrapper.text()).toContain('7×4')
    expect(wrapper.text()).toContain('three_side_3m')
  })

  it('reads packed dimensions from layout object when top-level n_long/n_short absent', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: '次果暂存间',
            temperature_band: '8~10℃',
            design_storage_mass_kg: 1000,
            position_count: 12,
            required_area_m2: 180,
            n_need: 10,
            layout: { n_long: 5, n_short: 3 }
          }
        ]
      }
    })

    expect(wrapper.text()).toContain('5×3')
  })

  it('shows shipping dock counts when present', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
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
        ]
      }
    })

    expect(wrapper.text()).toContain('出货通道')
    expect(wrapper.text()).toContain('托盘 42')
    expect(wrapper.text()).toContain('车数 3')
    expect(wrapper.text()).toContain('月台 2')
    expect(wrapper.text()).toContain('110 m²')
  })

  it('does not fabricate zero for absent optional dock fields', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: {
        zones: [
          {
            zone_name: '成品间',
            temperature_band: '1~3℃',
            design_storage_mass_kg: 5000,
            position_count: 20,
            required_area_m2: 300
          }
        ]
      }
    })

    expect(wrapper.text()).not.toContain('托盘')
    expect(wrapper.text()).not.toContain('车数')
    expect(wrapper.text()).not.toContain('月台')
    expect(wrapper.find('.zone-results-table__detail-row').exists()).toBe(false)
  })

  it('shows empty state when zones array is empty', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: { zones: [] }
    })

    expect(wrapper.find('.zone-results-table__empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无区域规划数据')
  })

  it('does not render a table when zones array is empty', () => {
    const wrapper = mount(ZoneResultsTable, {
      props: { zones: [] }
    })

    expect(wrapper.find('table').exists()).toBe(false)
  })
})
