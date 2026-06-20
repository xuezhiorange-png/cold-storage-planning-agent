import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import App from '../src/App.vue'

describe('cold storage workbench', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('keeps structured pages as the primary workflow', async () => {
    const wrapper = mount(App)

    expect(wrapper.find('.workflow-nav').text()).not.toContain('设计参数')
    expect(wrapper.text()).toContain('日处理量')
    expect(wrapper.text()).not.toContain('用户确认值')
    expect(wrapper.find('button.ai-icon-button').exists()).toBe(true)
    expect(wrapper.find('button.ai-icon-button').attributes('aria-label')).toBe('打开AI助手')
    expect(wrapper.find('.agent-panel').exists()).toBe(false)

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '基本信息')?.trigger('click')

    expect(wrapper.text()).toContain('总体情况')
    expect(wrapper.find('input[aria-label="加工厂名称"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="定植亩数"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="定植面积"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="定植品种"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="日处理量"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="包材库库存天数"]').exists()).toBe(true)
    expect(wrapper.find('.module-card').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('覆盖定植面积1250亩')
    expect(wrapper.text()).not.toContain('用户确认值')

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '计算结果')?.trigger('click')

    expect(wrapper.find('table.calculation-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('区域')
    expect(wrapper.text()).toContain('一级预冷间')
    expect(wrapper.text()).toContain('总面积')
    expect(wrapper.text()).not.toContain('承担产量')
    expect(wrapper.text()).not.toContain('温区')

    expect(wrapper.find('.workflow-nav').text()).toContain('用电估算')
    expect(wrapper.find('.workflow-nav').text()).toContain('投资估算')
    expect(wrapper.find('.workflow-nav').text()).not.toContain('投资用电')

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '投资估算')?.trigger('click')

    expect(wrapper.text()).toContain('投资估算')
    expect(wrapper.find('table.investment-estimate-table').exists()).toBe(true)
    expect(wrapper.findAll('table.investment-estimate-table thead th').map((cell) => cell.text())).toEqual([
      '投资分项',
      '估算金额'
    ])
    expect(wrapper.text()).toContain('土建及钢结构')
    expect(wrapper.text()).toContain('冷库制冷设备')
    expect(wrapper.text()).toContain('高低压配电')
    expect(wrapper.text()).toContain('住宿及生活区')
    expect(wrapper.text()).toContain('监控及开厂物资')
    expect(wrapper.text()).not.toContain('用电配置统计')

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '用电估算')?.trigger('click')

    const powerSection = wrapper.find('section[aria-label="用电配置"]')
    expect(powerSection.text()).toContain('用电配置统计')
    expect(powerSection.text()).not.toContain('投资估算')
    expect(wrapper.find('table.investment-estimate-table').exists()).toBe(false)
    expect(wrapper.find('table.power-config-table').exists()).toBe(true)
    expect(wrapper.findAll('table.power-config-table thead th').map((cell) => cell.text())).toEqual([
      '序号',
      '名称',
      '区域',
      '数量',
      '功率',
      '总功率'
    ])
    expect(wrapper.find('.power-row').exists()).toBe(false)
    expect(wrapper.text()).toContain('1352.63 kW')
    expect(wrapper.text()).toContain('轴流风机')
    expect(wrapper.text()).toContain('光电分选设备')
    expect(wrapper.text()).toContain('熏蒸设备')
  })

  it('renders sample content for main workflow pages', async () => {
    const wrapper = mount(App)
    const expectedByView: Record<string, string[]> = {
      基本信息: ['总体情况', '加工厂名称', '定植亩数', '定植品种', '日处理量', '包材库存'],
      计算结果: ['区域', '设计存储量', '板位数量', '估算面积', '成品间'],
      方案比选: ['方案评分对比', '总分'],
      投资估算: ['投资估算', '土建及钢结构', '冷库制冷设备', '高低压配电'],
      用电估算: ['用电配置统计', '熏蒸设备'],
      报告输出: ['报告生成队列', '方案书草稿']
    }

    for (const [view, expectedTexts] of Object.entries(expectedByView)) {
      await wrapper.findAll('.workflow-nav button').find((button) => button.text() === view)?.trigger('click')

      for (const text of expectedTexts) {
        expect(wrapper.text()).toContain(text)
      }
      expect(wrapper.text()).not.toContain('该页面保留结构化操作入口')
      expect(wrapper.text()).not.toContain('用户确认值')
    }
  })

  it('shows the main workflow as direct process navigation', async () => {
    const wrapper = mount(App)

    expect(wrapper.find('.project-header').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('概念设计')
    const workflow = wrapper.find('.workflow-nav')
    expect(workflow.exists()).toBe(true)
    expect(workflow.text()).toContain('基本信息')
    expect(workflow.text()).toContain('计算结果')
    expect(workflow.text()).toContain('投资估算')
    expect(workflow.text()).toContain('用电估算')
    expect(workflow.text()).toContain('报告输出')
    expect(workflow.text()).not.toContain('设计参数')

    await workflow.findAll('button').find((button) => button.text() === '基本信息')?.trigger('click')
    expect(wrapper.text()).toContain('总体情况')

    await workflow.findAll('button').find((button) => button.text() === '报告输出')?.trigger('click')
    expect(wrapper.text()).toContain('报告生成队列')
  })

  it('renders calculation results as a compact table', async () => {
    const wrapper = mount(App)

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '计算结果')?.trigger('click')

    expect(wrapper.find('table.calculation-table').exists()).toBe(true)
    expect(wrapper.find('table.calculation-table thead').text()).toContain('估算面积')
    expect(wrapper.findAll('table.calculation-table thead th').map((cell) => cell.text())).toEqual([
      '区域',
      '估算面积',
      '设计存储量',
      '板位数量'
    ])
    expect(wrapper.find('table.calculation-table thead').text()).not.toContain('承担产量')
    expect(wrapper.find('table.calculation-table thead').text()).not.toContain('温区')
    expect(wrapper.findAll('table.calculation-table tbody tr')).toHaveLength(11)
    expect(wrapper.find('table.calculation-table tfoot').text()).toContain('1813.57 m²')
  })

  it('keeps the calculation table from forcing horizontal scrolling on mobile', () => {
    const css = readFileSync(resolve(__dirname, '../src/style.css'), 'utf8')

    const calculationTableRule = css.match(/\.calculation-table\s*\{[^}]*\}/)?.[0] ?? ''

    expect(calculationTableRule).toContain('table-layout: fixed')
    expect(calculationTableRule).not.toContain('min-width')
    expect(css).toContain('@media (max-width: 980px)')
    expect(css).toContain('font-size: 13px')
  })

  it('keeps the basic information fields in three compact columns on mobile', () => {
    const css = readFileSync(resolve(__dirname, '../src/style.css'), 'utf8')
    const mobileCss = css.slice(css.indexOf('@media (max-width: 980px)'))
    const overviewFieldsRule = mobileCss.match(/\.overview-fields\s*\{[^}]*\}/)?.[0] ?? ''

    expect(overviewFieldsRule).toContain('grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.8fr) minmax(0, 1fr)')
    expect(overviewFieldsRule).not.toContain('grid-template-columns: 1fr')
    expect(mobileCss).toContain('.overview-fields label')
    expect(mobileCss).toContain('font-size: 11px')
  })

  it('uses a deep-blue workbench style and top AI icon entry', async () => {
    const css = readFileSync(resolve(__dirname, '../src/style.css'), 'utf8')
    const wrapper = mount(App)

    expect(css).toContain('#0b1f3a')
    expect(css).toContain('#123a63')
    expect(wrapper.find('.agent-popover').exists()).toBe(false)
    expect(wrapper.find('.agent-panel').exists()).toBe(false)
    await wrapper.find('button.ai-icon-button').trigger('click')
    expect(wrapper.find('.agent-popover').exists()).toBe(true)
    expect(wrapper.find('.agent-popover').text()).toContain('AI 助手')
  })

  it('keeps the planning parameter form compact across columns on mobile', () => {
    const css = readFileSync(resolve(__dirname, '../src/style.css'), 'utf8')
    const planningFormRule = css.match(/\.planning-form\s*\{[^}]*\}/)?.[0] ?? ''
    const mobileCss = css.slice(css.indexOf('@media (max-width: 980px)'))
    const mobilePlanningFormRule = mobileCss.match(/\.planning-form\s*\{[^}]*\}/)?.[0] ?? ''
    const mobilePlanningInputRule = mobileCss.match(/\.planning-form input\s*\{[^}]*\}/)?.[0] ?? ''
    const mobilePlanningLabelRule = mobileCss.match(/\.planning-form label span\s*\{[^}]*\}/)?.[0] ?? ''

    expect(planningFormRule).toContain('display: grid')
    expect(planningFormRule).toContain('repeat(auto-fit, minmax(92px, 1fr))')
    expect(mobilePlanningFormRule).toContain('repeat(auto-fit, minmax(82px, 1fr))')
    expect(mobilePlanningInputRule).toContain('font-size: 13px')
    expect(mobilePlanningInputRule).not.toContain('font-size: 16px')
    expect(mobilePlanningLabelRule).toContain('font-size: 11px')
  })

  it('lets the project overview edit factory name, planting mu count, and varieties', async () => {
    const wrapper = mount(App)

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '基本信息')?.trigger('click')

    expect(wrapper.find('input[aria-label="加工厂名称"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="定植亩数"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="定植面积"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="定植品种"]').exists()).toBe(true)

    await wrapper.find('input[aria-label="加工厂名称"]').setValue('元谋蓝莓加工厂')
    await wrapper.find('input[aria-label="定植亩数"]').setValue('1500')
    await wrapper.find('input[aria-label="定植品种"]').setValue('珠宝蓝、绿宝石')

    expect((wrapper.find('input[aria-label="加工厂名称"]').element as HTMLInputElement).value).toBe(
      '元谋蓝莓加工厂'
    )
    expect((wrapper.find('input[aria-label="定植亩数"]').element as HTMLInputElement).value).toBe(
      '1500'
    )
    expect((wrapper.find('input[aria-label="定植品种"]').element as HTMLInputElement).value).toBe(
      '珠宝蓝、绿宝石'
    )
    expect(wrapper.text()).not.toContain('对应峰值产量')
  })

  it('does not show a menu button or drawer', async () => {
    const wrapper = mount(App)

    expect(wrapper.find('.app-topbar').text()).toContain('冷库规划设计助手V1')
    expect(wrapper.find('button[aria-label="打开页面菜单"]').exists()).toBe(false)
    expect(wrapper.find('.sidebar').exists()).toBe(false)
  })

  it('runs planning from editable production inputs and renders returned results', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        input_snapshot: {
          daily_inbound_mass_kg: 30000,
          working_time_h_per_day: 16,
          utilization_factor: 0.85,
          finished_storage_days: 4,
          packaging_storage_days: 10,
          precooling_required_ratio: 0.8
        },
        summary: {
          total_area_m2: 853.42,
          total_position_count: 300,
          total_investment_cny: 3947223.5,
          total_power_kw: 1760.97,
          requires_review: true
        },
        power_configuration: {
          equipment_rows: [
            {
              sequence: 1,
              name: '制冷压缩机组',
              area: '一级预冷、原果暂存间、分选间',
              quantity: 1.2,
              defrost_power_kw: null,
              defrost_total_power_kw: null,
              running_power_kw: 297.6,
              total_power_kw: 357.12
            },
            {
              sequence: 7,
              name: '冷风机',
              area: '一级预冷间',
              quantity: 12,
              defrost_power_kw: 16.2,
              defrost_total_power_kw: 194.4,
              running_power_kw: 2.7,
              total_power_kw: 32.16
            }
          ],
          summary_rows: [
            { name: '制冷总功率', basis: '化霜同时系数30% + 设备运行同时系数90%', total_power_kw: 1419.69 },
            { name: '生产设备总功率', basis: '按90% 同时使用系数', total_power_kw: 341.28 },
            { name: '合计', basis: '', total_power_kw: 1760.97 }
          ],
          items: [
            { category: '制冷系统', installed_power_kw: 154.2, demand_factor: 0.75, estimated_demand_kw: 115.65 },
            { category: '分选包装工艺', installed_power_kw: 45, demand_factor: 0.7, estimated_demand_kw: 31.5 }
          ],
          total_installed_power_kw: 1760.97,
          total_estimated_demand_kw: 171.44,
          requires_review: true
        },
        zone_plan: {
          result: {
            zones: [
              {
                zone_name: '成品间',
                temperature_band: '1~3℃',
                daily_throughput_kg: 30000,
                design_storage_mass_kg: 90000,
                position_count: 180,
                required_area_m2: 416.67
              }
            ]
          }
        },
        investment_estimate: {
          result: {
            items: [
              { item_name: '土建及钢结构', amount_cny: 1668078 },
              { item_name: '冷库制冷设备', amount_cny: 1194788 },
              { item_name: '高低压配电', amount_cny: 884357.5 },
              { item_name: '住宿及生活区', amount_cny: 0 },
              { item_name: '监控及开厂物资', amount_cny: 200000 }
            ]
          }
        }
      })
    } as Response)

    const wrapper = mount(App)
    await wrapper.find('input[aria-label="日处理量"]').setValue('30')
    await wrapper.find('input[aria-label="成品库库存天数"]').setValue('4')
    await wrapper.find('input[aria-label="包材库库存天数"]').setValue('10')
    await wrapper.find('input[aria-label="辅助包材库存天数"]').setValue('20')
    await wrapper.find('input[aria-label="一级预冷工作时间"]').setValue('5')
    await wrapper.find('input[aria-label="冻果比例"]').setValue('0.06')
    await wrapper.find('button.run-planning').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('高峰系数')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/demo/planning-run',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"main_packaging_storage_days":10')
      })
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/demo/planning-run',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"auxiliary_packaging_storage_days":20')
      })
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/demo/planning-run',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"primary_precooling_working_hours_per_day":5')
      })
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/demo/planning-run',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"frozen_fruit_ratio":0.06')
      })
    )
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/v1/demo/planning-run',
      expect.objectContaining({
        body: expect.stringContaining('peak_factor')
      })
    )
    expect(wrapper.text()).toContain('853.42 m²')
    expect(wrapper.text()).toContain('394.72 万元')
    expect(wrapper.text()).toContain('1760.97 kW')

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '计算结果')?.trigger('click')
    expect(wrapper.find('table.calculation-table').exists()).toBe(true)

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '投资估算')?.trigger('click')
    expect(wrapper.text()).toContain('投资估算')
    expect(wrapper.text()).toContain('394.72 万元')

    await wrapper.findAll('.workflow-nav button').find((button) => button.text() === '用电估算')?.trigger('click')
    expect(wrapper.text()).toContain('制冷压缩机组')
    expect(wrapper.text()).toContain('一级预冷间')
    expect(wrapper.text()).toContain('制冷总功率')
    expect(wrapper.text()).toContain('1760.97 kW')
    expect(wrapper.find('section[aria-label="用电配置"]').text()).not.toContain('投资估算')
  })
})
