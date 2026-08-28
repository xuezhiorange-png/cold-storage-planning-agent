import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import InvestmentResultsTable from './InvestmentResultsTable.vue'

function investmentRecord(result: Record<string, unknown>): CalculationRunRecord {
  return {
    id: 'calc-investment',
    project_id: 'proj-1',
    project_version_id: 'ver-1',
    calculator_name: 'investment_estimate',
    calculator_version: '1.0.0',
    result_snapshot: {
      success: true,
      calculator_name: 'investment_estimate',
      calculator_version: '1.0.0',
      input: {},
      result
    },
    requires_review: false
  }
}

describe('InvestmentResultsTable', () => {
  it('shows empty copy when record is missing', () => {
    const wrapper = mount(InvestmentResultsTable, {
      props: { record: null }
    })
    expect(wrapper.text()).toContain('本阶段尚无持久化结果')
  })

  it('formats investment amounts in 万元 from persisted CNY', () => {
    const wrapper = mount(InvestmentResultsTable, {
      props: {
        record: investmentRecord({
          total_investment_cny: '500000',
          items: [
            { item_name: 'Compressor', amount_cny: '200000' },
            { item_name: 'Evaporator', amount_cny: '150000' }
          ]
        })
      }
    })

    expect(wrapper.text()).toContain('50.00')
    expect(wrapper.text()).toContain('20.00 万元')
    expect(wrapper.text()).toContain('Compressor')
    expect(wrapper.text()).toContain('投资分项')
  })
})
