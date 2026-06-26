import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import ProjectInputsPanel from './ProjectInputsPanel.vue'

describe('ProjectInputsPanel', () => {
  function createWrapper() {
    return mount(ProjectInputsPanel, {
      global: {
        plugins: [ElementPlus]
      }
    })
  }

  it('renders the card with header text', () => {
    const wrapper = createWrapper()

    expect(wrapper.text()).toContain('项目设计输入')
  })

  it('renders factory overview section', () => {
    const wrapper = createWrapper()

    expect(wrapper.text()).toContain('工厂概况')
    expect(wrapper.text()).toContain('工厂名称')
    expect(wrapper.text()).toContain('种植面积（亩）')
    expect(wrapper.text()).toContain('主要品种')
  })

  it('renders 工艺参数 section with all design input fields', () => {
    const wrapper = createWrapper()

    expect(wrapper.text()).toContain('工艺参数')
    expect(wrapper.text()).toContain('日入库量 (吨)')
    expect(wrapper.text()).toContain('每日工作时间 (小时)')
    expect(wrapper.text()).toContain('成品库库存天数')
    expect(wrapper.text()).toContain('主要包材库存天数')
    expect(wrapper.text()).toContain('辅助包材库存天数')
    expect(wrapper.text()).toContain('预冷比例')
    expect(wrapper.text()).toContain('原果暂存比例')
    expect(wrapper.text()).toContain('一级预冷工作时间 (小时)')
    expect(wrapper.text()).toContain('二级预冷工作时间 (小时)')
    expect(wrapper.text()).toContain('成品托位重量 (kg)')
    expect(wrapper.text()).toContain('冻果比例')
    expect(wrapper.text()).toContain('冻果库存天数')
    expect(wrapper.text()).toContain('冻果托位重量 (kg)')
  })

  it('renders the submit button', () => {
    const wrapper = createWrapper()

    expect(wrapper.text()).toContain('运行规划')
  })

  it('renders a reset button', () => {
    const wrapper = createWrapper()

    expect(wrapper.text()).toContain('重置')
  })

  it('has no error message initially', () => {
    const wrapper = createWrapper()

    expect(wrapper.find('.project-inputs-panel__error').exists()).toBe(false)
  })

  it('has a scoped style class on the root card', () => {
    const wrapper = createWrapper()

    expect(wrapper.classes()).toContain('project-inputs-panel')
  })
})
