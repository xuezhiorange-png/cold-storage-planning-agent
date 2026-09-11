import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { FactoryPowerPresentation } from '../../../api/contracts/factoryPower'
import FactoryPowerEstimationResults from './FactoryPowerEstimationResults.vue'

const presentation: FactoryPowerPresentation = {
  schema_version: '2.0.0-p1',
  source_calculator_id: 'factory_power_estimation',
  source_calculator_version: '2.0.0-p2',
  source_calculator_identity: 'factory_power_estimation@2.0.0-p2',
  canonical_result_hash: 'sha256:golden',
  factory_area_band: 'SMALL',
  unit_semantics: {
    power_unit: 'kW',
    energy_unit: 'kWh',
    not_energy: true,
    not_metered_electricity: true,
    not_daily_electricity_consumption: true
  },
  review: { requires_review: true, status: 'REQUIRES_ENGINEERING_REVIEW' },
  provenance: { rule_source: 'fixture' },
  assumptions: ['all values require engineering review'],
  details: [{
    equipment_or_zone: 'public.electric_sliding_door',
    display_label: '冷库电动平移门',
    pool_label: '其他设备',
    basis: 'factory_area_band',
    configured_quantity: 7,
    unit_power_kw: '0.5',
    installed_power_kw: '3.5',
    pool: 'POOL_B',
    simultaneity_factor: '0.8',
    coincident_power_kw: '123.456'
  }],
  summary: {
    defrost_installed_power_kw: '1',
    defrost_coincident_power_kw: '0.3',
    other_installed_power_kw: '3.5',
    other_coincident_power_kw: '123.456',
    production_equipment_installed_power_kw: '200',
    production_equipment_coincident_power_kw: '170',
    total_installed_power_kw: '204.5',
    estimated_total_power_kw: '999.999'
  }
}

describe('FactoryPowerEstimationResults', () => {
  it('renders the V2 canonical summary, detail, review, and audit metadata directly', () => {
    const wrapper = mount(FactoryPowerEstimationResults, {
      props: { presentation }
    })

    expect(wrapper.text()).toContain('估算工厂电功率（V2.0）')
    expect(wrapper.text()).toContain('999.999 kW')
    expect(wrapper.text()).toContain('204.5 kW')
    expect(wrapper.text()).toContain('化霜装机功率')
    expect(wrapper.text()).toContain('生产设备计入功率')
    expect(wrapper.text()).toContain('冷库电动平移门')
    expect(wrapper.text()).toContain('public.electric_sliding_door')
    expect(wrapper.text()).toContain('123.456 kW')
    expect(wrapper.text()).toContain('requires_review=true')
    expect(wrapper.text()).toContain('all values require engineering review')
    expect(wrapper.text()).toContain('fixture')
  })

  it('shows an explicit unavailable state and does not render a legacy result', () => {
    const wrapper = mount(FactoryPowerEstimationResults, {
      props: { presentation: null }
    })

    expect(wrapper.find('[data-testid="factory-power-estimation-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无可用的 V2.0 估算工厂电功率结果')
    expect(wrapper.text()).toContain('不会回退到旧装机功率或补充用电配置')
    expect(wrapper.text()).not.toContain('installed_power@1.0.0')
  })
})
