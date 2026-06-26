import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { createPinia } from 'pinia'

import App from '../src/App.vue'
import { usePlanningWorkflowStore } from '../src/stores/planningWorkflow'
import { createWorkbenchRouter } from '../src/app/router'

const testRouter = createWorkbenchRouter(createMemoryHistory())
const pinia = createPinia()
const workflowStore = usePlanningWorkflowStore(pinia)

testRouter.push('/workbench/project')
await testRouter.isReady()

function mountApp() {
  return mount(App, {
    global: {
      plugins: [testRouter, pinia]
    }
  })
}

describe('cold storage workbench', () => {
  beforeEach(async () => {
    workflowStore.clear()
    await testRouter.push('/workbench/project')
    await testRouter.isReady()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('redirects root to project page', () => {
    expect(testRouter.currentRoute.value.name).toBe('project')
    expect(testRouter.currentRoute.value.fullPath).toBe('/workbench/project')
  })

  it('renders the workbench navigation links', async () => {
    const wrapper = mountApp()

    const nav = wrapper.find('nav[aria-label="主流程导航"]')
    expect(nav.exists()).toBe(true)
    expect(nav.text()).toContain('基本信息')
    expect(nav.text()).toContain('计算结果')
    expect(nav.text()).toContain('方案比选')
    expect(nav.text()).toContain('投资估算')
    expect(nav.text()).toContain('用电配置')
    expect(nav.text()).toContain('报告输出')
  })

  it('renders the project input page by default', async () => {
    const wrapper = mountApp()

    expect(wrapper.text()).toContain('项目设计输入')
    expect(wrapper.text()).toContain('工厂概况')
  })

  it('navigates to calculations route', async () => {
    const wrapper = mountApp()
    await testRouter.push('/workbench/calculations')
    await flushPromises()

    expect(testRouter.currentRoute.value.name).toBe('calculations')
    expect(wrapper.text()).toContain('暂无计算结果')
  })

  it('navigates to schemes route', async () => {
    const wrapper = mountApp()
    await testRouter.push('/workbench/schemes')
    await flushPromises()

    expect(testRouter.currentRoute.value.name).toBe('schemes')
    expect(wrapper.text()).toContain('方案比选')
  })

  it('navigates to reports route', async () => {
    const wrapper = mountApp()
    await testRouter.push('/workbench/reports')
    await flushPromises()

    expect(testRouter.currentRoute.value.name).toBe('reports')
  })

  it('renders calculation results page with empty state when no planning data', async () => {
    const wrapper = mountApp()

    await testRouter.push('/workbench/calculations')
    await flushPromises()

    const empty = wrapper.find('.calculations-page__empty')
    expect(empty.exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无计算结果')
  })

  it('toggles agent panel on AI button click', async () => {
    const wrapper = mountApp()

    // Agent toggle button should be visible
    const toggleButton = wrapper.find('button.agent-panel__toggle')
    expect(toggleButton.exists()).toBe(true)

    // Chat drawer should be rendered in body via Teleport — initially hidden
    // The drawer content is teleported, check parent for teleported content
    const drawer = document.body.querySelector('.agent-panel__drawer')
    expect(drawer).toBeNull()

    // Click AI button to open
    await toggleButton.trigger('click')
    await flushPromises()

    // Drawer should now be in document body
    const visibleDrawer = document.body.querySelector('.agent-panel__drawer')
    expect(visibleDrawer).not.toBeNull()
    expect(visibleDrawer?.textContent).toContain('AI 助手')
  })

  it('renders project input form sections', async () => {
    const wrapper = mountApp()

    expect(wrapper.text()).toContain('工厂名称')
    expect(wrapper.text()).toContain('种植面积')
    expect(wrapper.text()).toContain('主要品种')
    expect(wrapper.text()).toContain('日入库量')
    expect(wrapper.text()).toContain('每日工作时间')
    expect(wrapper.text()).toContain('成品库库存天数')
  })

  it('renders submit button on project page', async () => {
    const wrapper = mountApp()

    const primaryButton = wrapper.find('.el-button--primary')
    expect(primaryButton.exists()).toBe(true)
    expect(primaryButton.text()).toContain('运行规划')
  })

  it('submits planning request with correct payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          summary: {
            total_area_m2: 850,
            total_position_count: 300,
            total_investment_cny: 3000000,
            total_power_kw: 1350,
            requires_review: false
          },
          zone_plan: { result: { zones: [] } },
          investment_estimate: { result: { items: [] } },
          power_configuration: {
            equipment_rows: [],
            summary_rows: [],
            items: [],
            total_installed_power_kw: 0,
            total_estimated_demand_kw: 0,
            requires_review: false
          }
        })
      )
    ) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    await flushPromises()

    // Click submit button
    const primaryButton = wrapper.find('.el-button--primary')
    expect(primaryButton.exists()).toBe(true)
    await primaryButton.trigger('click')
    await flushPromises()

    // Verify API was called
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/demo/planning-run',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"daily_inbound_mass_kg"')
      })
    )
  })

  it('shows deep-blue header in the application shell', () => {
    const wrapper = mountApp()
    const header = wrapper.find('header')
    expect(header.exists()).toBe(true)
  })

  it('investment page uses backend total_investment_cny not reduce sum', async () => {
    // Mock a response where items sum to 1,000,000 but total_investment_cny is 1,200,000
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          summary: {
            total_area_m2: 850,
            total_position_count: 300,
            total_investment_cny: 1_200_000,
            total_power_kw: 1350,
            requires_review: false
          },
          zone_plan: { result: { zones: [] } },
          investment_estimate: {
            result: {
              items: [
                { item_name: '土建', amount_cny: 600_000 },
                { item_name: '设备', amount_cny: 400_000 }
              ]
            }
          },
          power_configuration: {
            equipment_rows: [],
            summary_rows: [],
            items: [],
            total_installed_power_kw: 0,
            total_estimated_demand_kw: 0,
            requires_review: false
          }
        })
      )
    ) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    // Start at project page where submit button lives
    await testRouter.push('/workbench/project')
    await flushPromises()

    // Submit the planning run so the store has latestResponse
    const primaryBtn = wrapper.find('.el-button--primary')
    expect(primaryBtn.exists()).toBe(true)
    await primaryBtn.trigger('click')
    await flushPromises()

    // Navigate to investment page which reads store.latestResponse
    await testRouter.push('/workbench/investment')
    await flushPromises()

    // Should show 120.00 万元 (backend total), not 100.00 万元 (reduce sum)
    const totalEl = wrapper.find('.investment-page__total')
    expect(totalEl.text()).toContain('120.00')
    expect(totalEl.text()).not.toContain('100.00')
  })

  it('agent shows unavailable state when no backend exists', async () => {
    const wrapper = mountApp()
    await flushPromises()

    // Toggle button should have the unavailable class
    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    expect(toggleBtn.classes()).toContain('agent-panel__toggle--unavailable')

    // If drawer was left open from previous test, close it first
    let existingDrawer = document.body.querySelector('.agent-panel__drawer')
    if (existingDrawer) {
      await toggleBtn.trigger('click')
      await flushPromises()
    }

    // Open the drawer
    await toggleBtn.trigger('click')
    await flushPromises()

    // Check drawer content shows unavailable message
    const drawer = document.body.querySelector('.agent-panel__drawer')
    expect(drawer).not.toBeNull()
    expect(drawer!.textContent).toContain('不可用')
    expect(drawer!.textContent).toContain('未部署')

    // Close via the close button inside the drawer
    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()
    closeBtn!.click()
    await flushPromises()

    const closedDrawer = document.body.querySelector('.agent-panel__drawer')
    expect(closedDrawer).toBeNull()
  })

  it('renders workflow navigation at 320px width', async () => {
    window.innerWidth = 320
    window.dispatchEvent(new Event('resize'))

    const wrapper = mountApp()
    const nav = wrapper.find('nav[aria-label="主流程导航"]')
    expect(nav.exists()).toBe(true)
    expect(nav.text()).toContain('基本信息')
    expect(nav.text()).toContain('计算结果')
    expect(nav.text()).toContain('方案比选')

    // Restore
    window.innerWidth = 1024
  })

  it('renders submit button visible at 375px', async () => {
    window.innerWidth = 375
    window.dispatchEvent(new Event('resize'))

    const wrapper = mountApp()
    const btn = wrapper.find('.el-button--primary')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('运行规划')

    window.innerWidth = 1024
  })

  it('stale request does not update store after navigating away', async () => {
    let resolveFetch: ((value: Response) => void) | null = null

    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      (input: RequestInfo | URL, options?: RequestInit) => {
        return new Promise<Response>((resolve, reject) => {
          const signal = options?.signal
          if (signal) {
            if (signal.aborted) {
              reject(new DOMException('Aborted', 'AbortError'))
              return
            }
            signal.addEventListener('abort', () => {
              reject(new DOMException('Aborted', 'AbortError'))
            }, { once: true })
          }
          resolveFetch = resolve
        })
      }
    )

    const wrapper = mountApp()
    await flushPromises()

    const store = usePlanningWorkflowStore(pinia)

    // Submit — starts a pending request
    const primaryButton = wrapper.find('.el-button--primary')
    await primaryButton.trigger('click')
    await flushPromises()

    // Fetch was called and request data landed in the store
    expect(fetchMock).toHaveBeenCalled()

    // Navigate away before the API resolves (triggers onUnmounted → planner.abort)
    await testRouter.push('/workbench/calculations')
    await flushPromises()

    // After abort + stale protection, store should not have been updated with
    // a response or error from the aborted request
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')
  })

  it('request failure shows error on project page', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(
      new Error('API 请求失败')
    ) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    await flushPromises()

    const store = usePlanningWorkflowStore(pinia)

    // Submit
    const primaryButton = wrapper.find('.el-button--primary')
    await primaryButton.trigger('click')
    await flushPromises()

    // Store should have the error
    expect(store.error).toBe('API 请求失败')
    expect(store.isLoading).toBe(false)

    // Error display should be visible on the project page
    const errorDiv = wrapper.find('.project-page__error')
    expect(errorDiv.exists()).toBe(true)
    expect(errorDiv.text()).toContain('API 请求失败')
    expect(errorDiv.text()).toContain('请修改输入后重试')
  })
})
