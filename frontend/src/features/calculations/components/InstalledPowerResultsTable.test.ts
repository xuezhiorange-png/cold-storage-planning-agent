import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import InstalledPowerResultsTable from './InstalledPowerResultsTable.vue'

function powerRecord(result: Record<string, unknown>): CalculationRunRecord {
  return {
    id: 'calc-power',
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: 'installed_power',
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: 'installed_power',
      calculator_version: '1.0.0',
      input: {},
      result
    },
    requires_review: false
  }
}

describe('InstalledPowerResultsTable', () => {
  it('shows empty copy when record is missing', () => {
    const wrapper = mount(InstalledPowerResultsTable, {
      props: { record: null }
    })
    expect(wrapper.text()).toContain('本阶段尚无持久化结果')
  })

  it('reads installed_power authority fields, not power_configuration', () => {
    const wrapper = mount(InstalledPowerResultsTable, {
      props: {
        record: powerRecord({
          total_installed_power_kw_e: '250',
          total_estimated_demand_kw: '200',
          equipment_rows: [
            {
              sequence: 1,
              name: 'Compressor-1',
              area: 'machine_room',
              quantity: '1',
              running_power_kw: '50',
              total_power_kw: '50',
              section: 'compressor'
            }
          ],
          summary_rows: [
            { name: 'Compressor', basis: 'equipment', total_power_kw: '50' }
          ],
          items: [
            {
              category: 'compressor',
              installed_power_kw: '50',
              demand_factor: '0.8',
              estimated_demand_kw: '40'
            }
          ],
          assumptions: ['Using demo coefficients']
        })
      }
    })

    expect(wrapper.text()).toContain('250')
    expect(wrapper.text()).toContain('200')
    expect(wrapper.text()).toContain('Compressor-1')
    expect(wrapper.text()).toContain('compressor')
    expect(wrapper.text()).not.toContain('power_configuration')
  })
})
