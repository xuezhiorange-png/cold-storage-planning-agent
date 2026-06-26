import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { PlanningRunResponse } from '../../../api/contracts/planning'
import CalculationSummary from './CalculationSummary.vue'

function createSummary(
  overrides: Partial<PlanningRunResponse['summary']> = {}
): PlanningRunResponse['summary'] {
  return {
    total_area_m2: 1813.57,
    total_position_count: 346,
    total_investment_cny: 6_150_400,
    total_power_kw: 1352.63,
    requires_review: false,
    ...overrides
  }
}

describe('CalculationSummary', () => {
  it('renders four metric cards', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary() }
    })

    const cards = wrapper.findAll('.calculation-summary__card')
    expect(cards).toHaveLength(4)
  })

  it('displays the total area', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary({ total_area_m2: 2000 }) }
    })

    expect(wrapper.text()).toContain('2000 m²')
  })

  it('displays the total position count', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary({ total_position_count: 400 }) }
    })

    expect(wrapper.text()).toContain('400 个')
  })

  it('displays the total investment in 万元', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary({ total_investment_cny: 8_000_000 }) }
    })

    expect(wrapper.text()).toContain('800.00 万元')
  })

  it('displays the total power', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary({ total_power_kw: 1500 }) }
    })

    expect(wrapper.text()).toContain('1500 kW')
  })

  it('formats integer values without decimals', () => {
    const wrapper = mount(CalculationSummary, {
      props: {
        summary: createSummary({
          total_area_m2: 2000,
          total_position_count: 400,
          total_power_kw: 1200
        })
      }
    })

    expect(wrapper.text()).toContain('2000 m²')
    expect(wrapper.text()).toContain('400 个')
    expect(wrapper.text()).toContain('1200 kW')
  })

  it('shows a review notice when requires_review is true', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary({ requires_review: true }) }
    })

    expect(wrapper.find('.calculation-summary__notice').exists()).toBe(true)
  })

  it('hides the review notice when requires_review is false', () => {
    const wrapper = mount(CalculationSummary, {
      props: { summary: createSummary({ requires_review: false }) }
    })

    expect(wrapper.find('.calculation-summary__notice').exists()).toBe(false)
  })
})
