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
