import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import CoolingLoadResultsTable from './CoolingLoadResultsTable.vue'

function coolingRecord(
  result: Record<string, unknown>,
  extras: Partial<CalculationRunRecord> = {}
): CalculationRunRecord {
  return {
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
      result
    },
    requires_review: false,
    ...extras
  }
}

describe('CoolingLoadResultsTable', () => {
  it('shows empty copy when record is missing', () => {
    const wrapper = mount(CoolingLoadResultsTable, {
      props: { record: null }
    })
    expect(wrapper.text()).toContain('本阶段尚无持久化结果')
  })

  it('passes through persisted load fields without fabricating zeros', () => {
    const wrapper = mount(CoolingLoadResultsTable, {
      props: {
        record: coolingRecord({
          total_cooling_load_kw: '120.5',
          safety_margin_load_kw: '12.05',
          envelope_heat_transfer_load_kw: '30',
          product_sensible_heat_load_kw: '40',
          packaging_load_kw: '5',
          infiltration_load_kw: '10',
          personnel_load_kw: '3',
          lighting_load_kw: '2',
          evaporator_fan_load_kw: '15',
          defrost_additional_load_kw: '10',
          other_configuration_load_kw: '5.45'
        })
      }
    })

    expect(wrapper.text()).toContain('120.5')
    expect(wrapper.text()).toContain('总冷负荷')
    expect(wrapper.text()).not.toContain('0.00 kW(r)')
  })

  it('dual-reads nested result payload (V0.9 P6)', () => {
    const wrapper = mount(CoolingLoadResultsTable, {
      props: {
        record: {
          id: 'calc-cooling-nested',
          project_id: 'proj-1',
          project_version_id: 'ver-1',
          calculator_name: 'cooling_load',
          calculator_version: '1.0.0',
          result_snapshot: {
            success: true,
            calculator_name: 'cooling_load',
            calculator_version: '1.0.0',
            input: {},
            result: {
              result: {
                total_cooling_load_kw: '88.8',
                safety_margin_load_kw: '8.8',
                envelope_heat_transfer_load_kw: '10',
                product_sensible_heat_load_kw: '20',
                packaging_load_kw: '1',
                infiltration_load_kw: '2',
                personnel_load_kw: '1',
                lighting_load_kw: '1',
                evaporator_fan_load_kw: '2',
                defrost_additional_load_kw: '1',
                other_configuration_load_kw: '1'
              }
            }
          },
          requires_review: false
        }
      }
    })

    expect(wrapper.text()).toContain('88.8')
  })

  it('renders persisted formulas when present on record', () => {
    const wrapper = mount(CoolingLoadResultsTable, {
      props: {
        record: coolingRecord(
          {
            total_cooling_load_kw: '50',
            safety_margin_load_kw: '5',
            envelope_heat_transfer_load_kw: '10',
            product_sensible_heat_load_kw: '10',
            packaging_load_kw: '1',
            infiltration_load_kw: '1',
            personnel_load_kw: '1',
            lighting_load_kw: '1',
            evaporator_fan_load_kw: '1',
            defrost_additional_load_kw: '1',
            other_configuration_load_kw: '1'
          },
          {
            formulas: [
              {
                formula_id: 'Q_sensible',
                formula_version: '1.0',
                expression: 'Q = m * cp * dT',
                description: 'Sensible heat'
              }
            ]
          }
        )
      }
    })

    expect(wrapper.text()).toContain('Q = m * cp * dT')
    expect(wrapper.text()).toContain('Q_sensible')
  })
})
