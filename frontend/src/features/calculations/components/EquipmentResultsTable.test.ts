import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import EquipmentResultsTable from './EquipmentResultsTable.vue'

function equipmentRecord(result: Record<string, unknown>): CalculationRunRecord {
  return {
    id: 'calc-equipment',
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: 'equipment',
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: 'equipment',
      calculator_version: '1.0.0',
      input: {},
      result
    },
    requires_review: false
  }
}

describe('EquipmentResultsTable', () => {
  it('shows empty copy when record is missing', () => {
    const wrapper = mount(EquipmentResultsTable, {
      props: { record: null }
    })
    expect(wrapper.text()).toContain('本阶段尚无持久化结果')
  })

  it('passes through persisted equipment scalars', () => {
    const wrapper = mount(EquipmentResultsTable, {
      props: {
        record: equipmentRecord({
          evaporator_total_cooling_capacity_kw: '150',
          evaporator_quantity: 3,
          single_evaporator_capacity_kw: '50',
          compressor_operating_capacity_kw: '140',
          standby_capacity_kw: '20',
          condenser_heat_rejection_capacity_kw: '180',
          evaporation_temperature_c: '-35',
          condensing_temperature_c: '40',
          defrost_method: 'electric'
        })
      }
    })

    expect(wrapper.text()).toContain('150')
    expect(wrapper.text()).toContain('electric')
    expect(wrapper.text()).toContain('蒸发器总制冷量')
    expect(wrapper.text()).toContain('项目')
  })

  it('lists persisted systems array without deriving capacities', () => {
    const wrapper = mount(EquipmentResultsTable, {
      props: {
        record: equipmentRecord({
          evaporator_total_cooling_capacity_kw: '100',
          evaporator_quantity: 2,
          single_evaporator_capacity_kw: '50',
          compressor_operating_capacity_kw: '90',
          standby_capacity_kw: '10',
          condenser_heat_rejection_capacity_kw: '120',
          evaporation_temperature_c: '-30',
          condensing_temperature_c: '38',
          defrost_method: 'hot_gas',
          systems: [
            { system_code: 'S1', system_name: '冷冻系统', evaporator_quantity: 2 }
          ]
        })
      }
    })

    expect(wrapper.text()).toContain('S1')
    expect(wrapper.text()).toContain('冷冻系统')
    expect(wrapper.text()).toContain('系统编码')
    expect(wrapper.text()).toContain('系统名称')
  })
})
