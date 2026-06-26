import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { createPinia } from 'pinia'

import App from '../src/App.vue'
import { usePlanningWorkflowStore } from '../src/stores/planningWorkflow'
import { createWorkbenchRouter } from '../src/app/router'

// Mock element-plus ElMessage to prevent jsdom issues with toast creation
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...(actual as Record<string, unknown>),
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn()
    }
  }
})

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
    workflowStore.reset()
    await testRouter.push('/workbench/project')
    await testRouter.isReady()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    // Clean up any teleported drawer content left in the DOM
    document.body.querySelectorAll('.agent-panel__drawer, .agent-panel__overlay').forEach(el => el.remove())
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
    const store = usePlanningWorkflowStore(pinia)

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

    // Store state updated
    expect(store.isLoading).toBe(false)
    expect(store.latestResponse).not.toBeNull()
    expect(store.latestResponse?.summary.total_area_m2).toBe(850)
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

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    expect(toggleBtn.classes()).toContain('agent-panel__toggle--unavailable')
    expect(toggleBtn.attributes('aria-label')).toBe('查看 AI 助手不可用说明')

    // If drawer was left open from previous test, close it first
    let existingDrawer = document.body.querySelector('.agent-panel__drawer')
    if (existingDrawer) {
      await toggleBtn.trigger('click')
      await flushPromises()
    }

    // Open the drawer
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer')
    expect(drawer).not.toBeNull()
    expect(drawer!.textContent).toContain('AI 助手当前不可用')
    expect(drawer!.textContent).toContain('后端尚未部署')
    expect(drawer!.textContent).toContain('无法发送消息')

    // Close via the close button inside the drawer
    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()
    closeBtn!.click()
    await flushPromises()

    const closedDrawer = document.body.querySelector('.agent-panel__drawer')
    expect(closedDrawer).toBeNull()
  })

  /* ── Agent focus management ─────────────────────── */

  it('focuses close button when drawer opens', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement | null
    expect(drawer).not.toBeNull()

    // Close button should have focus (first focusable element)
    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()
    expect(document.activeElement).toBe(closeBtn)
  })

  it('Shift+Tab from close button stays inside drawer', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement | null
    expect(drawer).not.toBeNull()

    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()

    // Focus close button and Shift+Tab
    closeBtn!.focus()
    const shiftTabEvent = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true })
    closeBtn!.dispatchEvent(shiftTabEvent)

    // Focus should stay on closeBtn (only focusable element, cycles back)
    expect(document.activeElement).toBe(closeBtn)
  })

  it('Escape closes drawer', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement | null
    expect(drawer).not.toBeNull()

    // Escape
    const escEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    drawer!.dispatchEvent(escEvent)
    await flushPromises()

    // Drawer closed
    expect(document.body.querySelector('.agent-panel__drawer')).toBeNull()
  })

  it('close button click closes drawer', async () => {
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.find('button.agent-panel__toggle').trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement | null
    expect(drawer).not.toBeNull()

    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()
    closeBtn!.click()
    await flushPromises()

    expect(document.body.querySelector('.agent-panel__drawer')).toBeNull()
  })

  it('navigating to schemes route shows empty state', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => Promise.resolve(
        new Response(
          JSON.stringify({
            schemes: [],
            recommended_scheme_code: null,
            weight_set_name: '默认权重集',
            weight_set_status: 'verified'
          })
        )
      )
    ) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    await flushPromises()

    await testRouter.push('/workbench/schemes')
    await flushPromises()

    expect(wrapper.text()).toContain('暂无方案数据')
  })

  describe('narrow screen', () => {
    const widths = [320, 375, 768]

    widths.forEach(w => {
      it(`renders accessible workflow navigation at ${w}px`, async () => {
        window.innerWidth = w
        window.dispatchEvent(new Event('resize'))

        const wrapper = mountApp()

        const nav = wrapper.find('nav[aria-label="主流程导航"]')
        expect(nav.exists()).toBe(true)

        const links = nav.findAll('a')
        expect(links.length).toBe(6)

        for (const link of links) {
          expect(link.text().trim().length).toBeGreaterThan(0)
          expect(link.attributes('href')).toBeTruthy()
        }

        window.innerWidth = 1024
      })
    })

    it('nav uses flex-wrap or auto-scroll at 320px', async () => {
      window.innerWidth = 320
      window.dispatchEvent(new Event('resize'))

      const wrapper = mountApp()
      const nav = wrapper.find('nav[aria-label="主流程导航"]')
      expect(nav.isVisible()).toBe(true)

      const links = nav.findAll('a')
      expect(links.length).toBe(6)

      window.innerWidth = 1024
    })

    it('project page submit and reset buttons visible at 320px', async () => {
      window.innerWidth = 320
      window.dispatchEvent(new Event('resize'))

      const wrapper = mountApp()
      await flushPromises()

      const submitBtn = wrapper.find('.el-button--primary')
      expect(submitBtn.exists()).toBe(true)
      expect(submitBtn.isVisible()).toBe(true)

      const buttons = wrapper.findAll('.project-inputs-panel__header .el-button')
      expect(buttons.length).toBeGreaterThanOrEqual(1)

      window.innerWidth = 1024
    })

    it('agent toggle visible and clickable at 375px', async () => {
      window.innerWidth = 375
      window.dispatchEvent(new Event('resize'))

      const wrapper = mountApp()
      await flushPromises()

      const toggleBtn = wrapper.find('button.agent-panel__toggle')
      expect(toggleBtn.exists()).toBe(true)
      expect(toggleBtn.isVisible()).toBe(true)
      expect(toggleBtn.attributes('disabled')).toBeUndefined()

      window.innerWidth = 1024
    })
  })

  it('stale request does not update store when superseded by newer request', async () => {
    let resolveA: ((v: Response) => void) | null = null
    let resolveB: ((v: Response) => void) | null = null

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input: RequestInfo | URL, options?: RequestInit) => {
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
          // First call → resolveA, second call → resolveB
          if (!resolveA) {
            resolveA = resolve
          } else {
            resolveB = resolve
          }
        })
      }
    )

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // 1. Submit A through the real UI
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)
    expect(store.latestRequest).not.toBeNull()

    // 2. Execute request B — cancels A, starts B (deferred)
    store.execute({
      daily_inbound_mass_kg: 200,
      working_time_h_per_day: 10,
      utilization_factor: 0.85,
      finished_storage_days: 10,
      packaging_storage_days: 5,
      main_packaging_storage_days: 2,
      auxiliary_packaging_storage_days: 2,
      reserve_factor: 1.1,
      precooling_required_ratio: 0.9,
      primary_precooling_working_hours_per_day: 8,
      secondary_precooling_working_hours_per_day: 8,
      raw_storage_ratio: 0.4,
      finished_goods_pallet_weight_kg: 600,
      frozen_fruit_ratio: 0.3,
      frozen_storage_days: 45,
      frozen_goods_pallet_weight_kg: 600
    })
    await flushPromises()

    // B is now in-flight
    expect(store.isLoading).toBe(true)

    // 3. Resolve B first
    const bResponse = {
      success: true,
      summary: { total_area_m2: 850, total_position_count: 300, total_investment_cny: 3_000_000, total_power_kw: 1350, requires_review: false },
      zone_plan: { result: { zones: [] } },
      investment_estimate: { result: { items: [] } },
      power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false }
    }
    if (resolveB) (resolveB as (v: Response) => void)(new Response(JSON.stringify(bResponse)))
    await flushPromises()

    // Store has B's response
    expect(store.isLoading).toBe(false)
    expect(store.latestResponse).not.toBeNull()
    expect(store.latestResponse!.summary.total_area_m2).toBe(850)

    // 4. Try to resolve A (was already aborted — resolve is a no-op)
    const aResponse = {
      success: true,
      summary: { total_area_m2: 999, total_position_count: 1, total_investment_cny: 1_000_000, total_power_kw: 100, requires_review: false },
      zone_plan: { result: { zones: [] } },
      investment_estimate: { result: { items: [] } },
      power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false }
    }
    if (resolveA) (resolveA as (v: Response) => void)(new Response(JSON.stringify(aResponse)))
    await flushPromises()

    // Store must still have B's response — A was discarded
    expect(store.latestResponse!.summary.total_area_m2).toBe(850)
  })

  it('successful planning end-to-end: submit -> store -> navigate -> render calculations', async () => {
    const mockResponse = {
      success: true,
      summary: {
        total_area_m2: 850,
        total_position_count: 300,
        total_investment_cny: 3000000,
        total_power_kw: 1350,
        requires_review: false
      },
      zone_plan: {
        result: {
          zones: [
            { zone_name: '原料暂存', temperature_band: '常温', daily_throughput_kg: 12000, design_storage_mass_kg: 24000, position_count: 80, required_area_m2: 200 },
            { zone_name: '成品冷藏', temperature_band: '冷藏', daily_throughput_kg: 15000, design_storage_mass_kg: 37500, position_count: 120, required_area_m2: 450 }
          ]
        }
      },
      investment_estimate: {
        result: {
          items: [
            { item_name: '土建', amount_cny: 600000 },
            { item_name: '设备', amount_cny: 400000 }
          ]
        }
      },
      power_configuration: {
        equipment_rows: [
          { sequence: 1, name: '压缩机组', area: '制冷机房', quantity: 2, running_power_kw: 120, total_power_kw: 240, defrost_power_kw: null, defrost_total_power_kw: null },
          { sequence: 2, name: '冷风机', area: '冷藏间', quantity: 6, running_power_kw: 3.5, total_power_kw: 21, defrost_power_kw: 9, defrost_total_power_kw: 54 }
        ],
        summary_rows: [{ name: '制冷系统', basis: '设备功率合计', total_power_kw: 261 }],
        items: [],
        total_installed_power_kw: 315,
        total_estimated_demand_kw: 220,
        requires_review: false
      }
    }

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockResponse))
    )

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // 1. Start at project page
    expect(testRouter.currentRoute.value.name).toBe('project')

    // 2. Submit
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()

    // 3. Request went through — store has the request
    expect(store.latestRequest).not.toBeNull()

    // 4. Store has the response
    expect(store.latestResponse).not.toBeNull()
    expect(store.latestResponse!.summary.total_area_m2).toBe(850)
    expect(store.latestResponse!.summary.total_position_count).toBe(300)
    expect(store.latestResponse!.summary.total_investment_cny).toBe(3000000)
    expect(store.latestResponse!.summary.total_power_kw).toBe(1350)
    expect(store.isLoading).toBe(false)

    // 5. Auto-navigation to calculations
    await flushPromises()
    expect(testRouter.currentRoute.value.name).toBe('calculations')

    // 6. Summary rendered
    expect(wrapper.text()).toContain('850')
    expect(wrapper.text()).toContain('300')

    // 7. Zone rows rendered
    expect(wrapper.text()).toContain('原料暂存')
    expect(wrapper.text()).toContain('成品冷藏')
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

  it('route unmount resolves store.isLoading after navigating away', async () => {
    let resolveFetch: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, options) => {
      return new Promise((resolve, reject) => {
        const signal = options?.signal
        if (signal) {
          if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
        }
        resolveFetch = resolve
      })
    })

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // Navigate away
    await testRouter.push('/workbench/calculations')
    await flushPromises()

    // isLoading must be false after route unmount
    expect(store.isLoading).toBe(false)
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')
  })

  it('reset during request cancels and clears store', async () => {
    let resolveFetch: ((v: Response) => void) | null = null
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, options) => {
      return new Promise((resolve, reject) => {
        const signal = options?.signal
        if (signal) {
          if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
        }
        resolveFetch = resolve
      })
    })

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // Reset
    store.reset()
    await flushPromises()

    // Store cleared, loading false
    expect(store.isLoading).toBe(false)
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')

    // Old response cannot write back
    if (resolveFetch) (resolveFetch as (v: Response) => void)(new Response(JSON.stringify({ success: true, summary: { total_area_m2: 999, total_position_count: 1, total_investment_cny: 0, total_power_kw: 0, requires_review: false }, zone_plan: { result: { zones: [] } }, investment_estimate: { result: { items: [] } }, power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false } })))
    await flushPromises()

    // Store should still be reset (old response not written back)
    expect(store.latestResponse).toBeNull()
  })

  it('run A then run B, A response does not overwrite B', async () => {
    let resolveA: ((v: Response) => void) | null = null
    let resolveB: ((v: Response) => void) | null = null

    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockImplementation((input, options) => {
      return new Promise((resolve, reject) => {
        const signal = options?.signal
        if (signal) {
          if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
        }
        if (!resolveA) {
          resolveA = resolve
        } else {
          resolveB = resolve
        }
      })
    })

    const store = usePlanningWorkflowStore(pinia)

    // Execute A
    store.execute({ daily_inbound_mass_kg: 100, working_time_h_per_day: 8, utilization_factor: 0.8, finished_storage_days: 7, packaging_storage_days: 7, main_packaging_storage_days: 3, auxiliary_packaging_storage_days: 3, reserve_factor: 1.2, precooling_required_ratio: 0.8, primary_precooling_working_hours_per_day: 6, secondary_precooling_working_hours_per_day: 6, raw_storage_ratio: 0.3, finished_goods_pallet_weight_kg: 500, frozen_fruit_ratio: 0.2, frozen_storage_days: 30, frozen_goods_pallet_weight_kg: 500 })
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // Execute B (cancels A)
    store.execute({ daily_inbound_mass_kg: 200, working_time_h_per_day: 10, utilization_factor: 0.85, finished_storage_days: 10, packaging_storage_days: 5, main_packaging_storage_days: 2, auxiliary_packaging_storage_days: 2, reserve_factor: 1.1, precooling_required_ratio: 0.9, primary_precooling_working_hours_per_day: 8, secondary_precooling_working_hours_per_day: 8, raw_storage_ratio: 0.4, finished_goods_pallet_weight_kg: 600, frozen_fruit_ratio: 0.3, frozen_storage_days: 45, frozen_goods_pallet_weight_kg: 600 })
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // B resolves
    const bResponseData = { success: true, summary: { total_area_m2: 200, total_position_count: 2, total_investment_cny: 0, total_power_kw: 0, requires_review: false }, zone_plan: { result: { zones: [] } }, investment_estimate: { result: { items: [] } }, power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false } }
    if (resolveB) (resolveB as (v: Response) => void)(new Response(JSON.stringify(bResponseData)))
    await flushPromises()

    expect(store.isLoading).toBe(false)
    expect(store.latestResponse?.summary.total_area_m2).toBe(200)
    expect(store.latestRequest?.daily_inbound_mass_kg).toBe(200)

    // A resolves (should be ignored)
    if (resolveA) (resolveA as (v: Response) => void)(new Response(JSON.stringify({ ...bResponseData, summary: { ...bResponseData.summary, total_area_m2: 999 } })))
    await flushPromises()

    expect(store.latestResponse?.summary.total_area_m2).toBe(200)
  })

  /* ── Agent toggle clickability & focus tests ──────── */

  it('unavailable toggle button is clickable (no pointer-events: none)', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    expect(toggleBtn.exists()).toBe(true)
    expect(toggleBtn.classes()).toContain('agent-panel__toggle--unavailable')

    const style = toggleBtn.attributes('style')
    if (style) {
      expect(style).not.toContain('pointer-events')
    }

    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer')
    expect(drawer).not.toBeNull()
    expect(drawer!.textContent).toContain('AI 助手当前不可用')

    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()
    closeBtn!.click()
    await flushPromises()
  })

  it('closes drawer on Escape and close button exists', async () => {
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement | null
    expect(drawer).not.toBeNull()

    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    expect(closeBtn).not.toBeNull()
    expect(closeBtn!.textContent).toContain('✕')

    const escEvent = new KeyboardEvent('keydown', {
      key: 'Escape',
      code: 'Escape',
      bubbles: true,
      cancelable: true
    })
    drawer!.dispatchEvent(escEvent)
    await flushPromises()

    const closedDrawer = document.body.querySelector('.agent-panel__drawer')
    expect(closedDrawer).toBeNull()
  })

  it('setTimeout is called on close for focus restore', async () => {
    vi.useFakeTimers()
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement | null
    const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
    closeBtn!.click()

    vi.advanceTimersByTime(100)
    await flushPromises()

    expect(document.body.querySelector('.agent-panel__drawer')).toBeNull()
    vi.useRealTimers()
  })

  it('reset button during request cancels store state and stays on project page', async () => {
    let resolveFetch: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, options) => {
      return new Promise((resolve, reject) => {
        const signal = options?.signal
        if (signal) {
          if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
        }
        resolveFetch = resolve
      })
    }) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit — request pending
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)
    expect(store.latestRequest).not.toBeNull()

    // Find and click the real reset button in ProjectInputsPanel
    const resetBtn = wrapper.findAll('button').filter(b => b.text().includes('重置'))[0]
    expect(resetBtn).toBeDefined()
    expect(resetBtn.text()).toContain('重置')
    await resetBtn.trigger('click')
    await flushPromises()

    // Store is now reset
    expect(store.isLoading).toBe(false)
    expect(store.latestRequest).toBeNull()
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')

    // Still on project page
    expect(testRouter.currentRoute.value.name).toBe('project')

    // Old request resolves — should not write back
    if (resolveFetch) {
      (resolveFetch as (v: Response) => void)(new Response(JSON.stringify({ success: true, summary: { total_area_m2: 999, total_position_count: 1, total_investment_cny: 0, total_power_kw: 0, requires_review: false }, zone_plan: { result: { zones: [] } }, investment_estimate: { result: { items: [] } }, power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false } })))
    }
    await flushPromises()

    // Old response NOT written back, still on project
    expect(store.latestResponse).toBeNull()
    expect(testRouter.currentRoute.value.name).toBe('project')
  })

  it('reset button during request restores form, clears store, aborts signal, stays on project', async () => {
    let capturedSignal: AbortSignal | null = null
    let resolveFetch: ((v: Response) => void) | null = null

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input: RequestInfo | URL, options?: RequestInit) => {
        capturedSignal = options?.signal ?? null
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

    // Submit click
    const submitBtn = wrapper.find('.el-button--primary')
    await submitBtn.trigger('click')
    await flushPromises()

    // submitting should be true, store loading true
    expect(store.isLoading).toBe(true)
    expect(store.latestRequest).not.toBeNull()

    // Capture signal before reset
    expect(capturedSignal).not.toBeNull()

    // Find and click reset button by text 重置
    const allButtons = wrapper.findAll('button')
    const resetButton = allButtons.filter(b => b.text().includes('重置'))
    expect(resetButton.length).toBeGreaterThanOrEqual(1)
    await resetButton[0].trigger('click')
    await flushPromises()

    // Store cleared
    expect(store.isLoading).toBe(false)
    expect(store.latestRequest).toBeNull()
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')

    // Signal should be aborted (reset cancels the request)
    expect((capturedSignal as unknown as AbortSignal).aborted).toBe(true)

    // Still on project
    expect(testRouter.currentRoute.value.name).toBe('project')

    // Resolve old request
    if (resolveFetch) {
      (resolveFetch as (v: Response) => void)(new Response(JSON.stringify({
        success: true,
        summary: { total_area_m2: 999, total_position_count: 1, total_investment_cny: 0, total_power_kw: 0, requires_review: false },
        zone_plan: { result: { zones: [] } },
        investment_estimate: { result: { items: [] } },
        power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false }
      })))
    }
    await flushPromises()

    // Old response not written back
    expect(store.latestResponse).toBeNull()
    expect(testRouter.currentRoute.value.name).toBe('project')
  })

  it('planning error stays on project page (no navigation)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(
      new Error('API 请求失败')
    ) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()

    // Store has the error
    expect(store.error).toBe('API 请求失败')
    expect(store.isLoading).toBe(false)

    // Still on project page — no navigation despite failing
    expect(testRouter.currentRoute.value.name).toBe('project')

    // Error display visible on project page
    const errorDiv = wrapper.find('.project-page__error')
    expect(errorDiv.exists()).toBe(true)
    expect(errorDiv.text()).toContain('API 请求失败')
    expect(errorDiv.text()).toContain('请修改输入后重试')
  })

  it('cancelled request stays on project page', async () => {
    let resolveFetch: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, options) => {
      return new Promise((resolve, reject) => {
        const signal = options?.signal
        if (signal) {
          if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
        }
        resolveFetch = resolve
      })
    }) as unknown as typeof globalThis.fetch

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // Cancel via store
    store.cancel()
    await flushPromises()

    // Store is cleared
    expect(store.isLoading).toBe(false)
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')

    // Still on project page — no navigation
    expect(testRouter.currentRoute.value.name).toBe('project')
  })

  it('pending A -> reset -> resolve A -> no navigation or store change', async () => {
    let resolveA: ((v: Response) => void) | null = null

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (input, options) => {
        return new Promise<Response>((resolve, reject) => {
          const signal = options?.signal
          if (signal) {
            if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
            signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
          }
          resolveA = resolve
        })
      }
    )

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit A
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // Reset
    const resetBtn = wrapper.findAll('button').filter(b => b.text().includes('重置'))
    if (resetBtn.length > 0) {
      await resetBtn[0].trigger('click')
    }
    await flushPromises()

    expect(store.isLoading).toBe(false)
    expect(store.latestRequest).toBeNull()
    expect(testRouter.currentRoute.value.name).toBe('project')

    // Resolve A
    if (resolveA) {
      (resolveA as (v: Response) => void)(new Response(JSON.stringify({
        success: true,
        summary: { total_area_m2: 999, total_position_count: 1, total_investment_cny: 0, total_power_kw: 0, requires_review: false },
        zone_plan: { result: { zones: [] } },
        investment_estimate: { result: { items: [] } },
        power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false }
      })))
    }
    await flushPromises()

    // Still no stale data or navigation
    expect(store.latestResponse).toBeNull()
    expect(testRouter.currentRoute.value.name).toBe('project')
  })

  it('pending A -> route unmount -> resolve A -> no stale update or navigation', async () => {
    let resolveA: ((v: Response) => void) | null = null

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (input, options) => {
        return new Promise<Response>((resolve, reject) => {
          const signal = options?.signal
          if (signal) {
            if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
            signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
          }
          resolveA = resolve
        })
      }
    )

    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)

    // Submit A
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    expect(store.isLoading).toBe(true)

    // Navigate to calculations (triggers onUnmounted → store.cancel())
    await testRouter.push('/workbench/calculations')
    await flushPromises()

    expect(store.isLoading).toBe(false)
    expect(store.latestResponse).toBeNull()

    // Resolve A
    if (resolveA) {
      (resolveA as (v: Response) => void)(new Response(JSON.stringify({
        success: true,
        summary: { total_area_m2: 999, total_position_count: 1, total_investment_cny: 0, total_power_kw: 0, requires_review: false },
        zone_plan: { result: { zones: [] } },
        investment_estimate: { result: { items: [] } },
        power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false }
      })))
    }
    await flushPromises()

    // No stale update
    expect(store.latestResponse).toBeNull()
  })
})
