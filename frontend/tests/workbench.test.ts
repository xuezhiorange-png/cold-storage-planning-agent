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
    },
    attachTo: document.body
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

  /* ── Agent focus restore and close path tests ──────── */

  it('opens drawer and focuses close button', async () => {
    const wrapper = mountApp()
    await flushPromises()

    await wrapper.find('button.agent-panel__toggle').trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement
    expect(drawer).not.toBeNull()
    const closeBtn = drawer.querySelector('.agent-panel__close-btn') as HTMLElement
    expect(closeBtn).not.toBeNull()
    expect(document.activeElement).toBe(closeBtn)
  })

  it('Escape closes drawer and restores focus to toggle', async () => {
    vi.useFakeTimers()

    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    // Focus toggle first
    ;(toggleBtn.element as HTMLElement).focus()

    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement
    expect(drawer).not.toBeNull()
    
    // Close button focused
    const closeBtn = drawer.querySelector('.agent-panel__close-btn') as HTMLElement
    expect(document.activeElement).toBe(closeBtn)

    // Escape
    drawer.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    await flushPromises()

    // Advance timers for focus restore
    vi.advanceTimersByTime(150)
    await flushPromises()

    // Drawer closed
    expect(document.body.querySelector('.agent-panel__drawer')).toBeNull()
    // Focus restored to toggle
    expect(document.activeElement).toBe(toggleBtn.element)

    vi.useRealTimers()
  })

  it('close and reopen within 100ms keeps focus on new close button', async () => {
    vi.useFakeTimers()
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')

    // Open
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer1 = document.body.querySelector('.agent-panel__drawer') as HTMLElement
    expect(drawer1).not.toBeNull()
    const closeBtn1 = drawer1.querySelector('.agent-panel__close-btn') as HTMLElement
    expect(document.activeElement).toBe(closeBtn1)

    // Close
    closeBtn1.click()
    await flushPromises()

    // Immediately reopen (before 100ms timer fires)
    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer2 = document.body.querySelector('.agent-panel__drawer') as HTMLElement
    expect(drawer2).not.toBeNull()
    const closeBtn2 = drawer2.querySelector('.agent-panel__close-btn') as HTMLElement
    // After reopening, close button should have focus
    expect(document.activeElement).toBe(closeBtn2)

    // Advance past the stale restore timer
    vi.advanceTimersByTime(150)
    await flushPromises()

    // Drawer still open, focus still on close button inside drawer
    expect(document.body.querySelector('.agent-panel__drawer')).not.toBeNull()
    expect(document.activeElement).toBe(closeBtn2)
    expect(drawer2.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).not.toBe(toggleBtn.element)

    vi.useRealTimers()
  })

  it('close button closes drawer and restores focus to toggle', async () => {
    vi.useFakeTimers()
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    ;(toggleBtn.element as HTMLElement).focus()

    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement
    const closeBtn = drawer.querySelector('.agent-panel__close-btn') as HTMLElement
    expect(closeBtn).not.toBeNull()
    expect(document.activeElement).toBe(closeBtn)

    closeBtn.click()
    await flushPromises()

    // Advance timers for focus restore
    vi.advanceTimersByTime(150)
    await flushPromises()

    expect(document.body.querySelector('.agent-panel__drawer')).toBeNull()
    expect(document.activeElement).toBe(toggleBtn.element)
    vi.useRealTimers()
  })

  it('overlay closes drawer and restores focus to toggle', async () => {
    vi.useFakeTimers()
    const wrapper = mountApp()
    await flushPromises()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    ;(toggleBtn.element as HTMLElement).focus()

    await toggleBtn.trigger('click')
    await flushPromises()

    const overlay = document.body.querySelector('.agent-panel__overlay') as HTMLElement
    expect(overlay).not.toBeNull()

    // Click overlay itself (not a child)
    overlay.click()
    await flushPromises()

    // Advance timers for focus restore
    vi.advanceTimersByTime(150)
    await flushPromises()

    expect(document.body.querySelector('.agent-panel__drawer')).toBeNull()
    expect(document.activeElement).toBe(toggleBtn.element)
    vi.useRealTimers()
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

    // —1— Modify at least 2 form fields before submit
    // Modify factory name (ElInput with placeholder)
    const factoryNameInput = wrapper.find('input[placeholder="输入工厂名称"]')
    expect(factoryNameInput.exists()).toBe(true)
    await factoryNameInput.setValue('测试用加工厂')

    // Modify daily inbound mass (ElInputNumber inside form item with label "日入库量")
    const formItems = wrapper.findAll('.el-form-item')
    const dailyInboundItem = formItems.filter(
      item => item.text().includes('日入库量')
    )[0]
    expect(dailyInboundItem).toBeDefined()
    const dailyInboundInput = dailyInboundItem.find('.el-input__inner')
    expect(dailyInboundInput.exists()).toBe(true)
    await dailyInboundInput.setValue(50)

    // Submit click
    const submitBtn = wrapper.find('.el-button--primary')
    await submitBtn.trigger('click')
    await flushPromises()

    // submitting should be true, button shows loading text, store loading true
    expect(submitBtn.text()).toContain('提交中...')
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

    // Button text should revert to idle state (no longer "提交中...")
    expect(submitBtn.text()).not.toContain('提交中...')
    expect(submitBtn.text()).toContain('运行规划')
    // Submit button should not be in loading state
    expect(submitBtn.classes()).not.toContain('is-loading')

    // Form fields restored to defaults
    const factoryNameAfter = wrapper.find('input[placeholder="输入工厂名称"]')
    expect((factoryNameAfter.element as HTMLInputElement).value).toBe('蓝莓加工厂')

    // Re-find daily inbound input after reset
    const formItemsAfter = wrapper.findAll('.el-form-item')
    const dailyInboundItemAfter = formItemsAfter.filter(
      item => item.text().includes('日入库量')
    )[0]
    const dailyInboundInputAfter = dailyInboundItemAfter.find('.el-input__inner')
    // Default dailyInboundMassTons is 25 (displayed as 25.0 due to precision=1)
    expect((dailyInboundInputAfter.element as HTMLInputElement).value).toBe('25.0')

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

    // Old response not written back, no error, no navigation
    expect(store.latestResponse).toBeNull()
    expect(store.error).toBe('')
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

describe('narrow screen nav link clicks', () => {
  beforeEach(async () => {
    workflowStore.reset()
    await testRouter.push('/workbench/project')
    await testRouter.isReady()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.querySelectorAll('.agent-panel__drawer, .agent-panel__overlay').forEach(el => el.remove())
  })

  const widths = [320, 375, 768]
  
  widths.forEach(w => {
    it(`click all 6 nav links at ${w}px`, async () => {
      window.innerWidth = w
      window.dispatchEvent(new Event('resize'))
      
      const wrapper = mountApp()
      await flushPromises()
      
      const nav = wrapper.find('nav[aria-label="主流程导航"]')
      expect(nav.exists()).toBe(true)
      
      const links = nav.findAll('a')
      expect(links.length).toBe(6)
      
      // Click each link by label and verify route via real link clicks.
      const expected: Record<string, string> = {
        '基本信息': '/workbench/project',
        '计算结果': '/workbench/calculations',
        '方案比选': '/workbench/schemes',
        '投资估算': '/workbench/investment',
        '用电配置': '/workbench/power',
        '报告输出': '/workbench/reports'
      }
      
      for (const [label, expectedPath] of Object.entries(expected)) {
        // Re-find links fresh each iteration (DOM changes after navigation)
        const refreshedNav = wrapper.find('nav[aria-label="主流程导航"]')
        const refreshedLinks = refreshedNav.findAll('a')
        const link = refreshedLinks.find(l => l.text().trim().startsWith(label))
        expect(link, `Link for "${label}" not found at ${w}px`).toBeTruthy()
        
        // Spy on push to capture the navigation promise returned by RouterLink's click handler
        const pushSpy = vi.spyOn(testRouter, 'push')
        
        // Use VTU trigger('click') to dispatch a real click event through Vue's event system
        await link!.trigger('click')
        await flushPromises()
        
        // Await the navigation promise that RouterLink's onClick handler returned from push()
        if (pushSpy.mock.results.length > 0) {
          const result = pushSpy.mock.results[0]
          if (result.type === 'return' && result.value instanceof Promise) {
            await result.value
          }
        }
        pushSpy.mockRestore()
        
        expect(testRouter.currentRoute.value.path,
          `Route mismatch after clicking "${label}" at ${w}px`
        ).toBe(expectedPath)
      }
      
      window.innerWidth = 1024
    })
  })
  
  it('table-scroll containers exist on calculations, power, investment pages', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
      summary: { total_area_m2: 850, total_position_count: 300, total_investment_cny: 3000000, total_power_kw: 1350, requires_review: false },
      zone_plan: { result: { zones: [{ zone_name: '原料暂存', temperature_band: '常温', daily_throughput_kg: 12000, design_storage_mass_kg: 24000, position_count: 80, required_area_m2: 200, area_m2: 200, cooling_load_kw: 45, design_temp_c: 0 }] } },
      investment_estimate: { result: { items: [{ item_name: '土建', amount_cny: 600000 }] } },
      power_configuration: {
        equipment_rows: [{ sequence: 1, name: '压缩机组', area: '制冷机房', quantity: 2, running_power_kw: 120, total_power_kw: 240, defrost_power_kw: null, defrost_total_power_kw: null }],
        summary_rows: [{ name: '制冷系统', basis: '设备功率合计', total_power_kw: 261 }],
        items: [],
        total_installed_power_kw: 315,
        total_estimated_demand_kw: 220,
        requires_review: false
      }
    })))
    
    const wrapper = mountApp()
    await flushPromises()
    const store = usePlanningWorkflowStore(pinia)
    
    // Submit to populate store
    await wrapper.find('.el-button--primary').trigger('click')
    await flushPromises()
    
    // Calculations
    await testRouter.push('/workbench/calculations')
    await flushPromises()
    const calcScroll = wrapper.find('.table-scroll')
    expect(calcScroll.exists()).toBe(true)
    
    // Power
    await testRouter.push('/workbench/power')
    await flushPromises()
    const powerScrolls = wrapper.findAll('.table-scroll')
    expect(powerScrolls.length).toBeGreaterThanOrEqual(2)
    
    // Investment
    await testRouter.push('/workbench/investment')
    await flushPromises()
    const invScroll = wrapper.find('.table-scroll')
    expect(invScroll.exists()).toBe(true)
  })

  it('reports exports table inside table-scroll with accessible download action', async () => {
    // Use mockImplementation to handle sequential fetch calls across planning and reports API
    const fetchMock = vi.spyOn(globalThis, 'fetch')

    let callCount = 0
    fetchMock.mockImplementation((url: RequestInfo | URL) => {
      callCount++
      const urlStr = String(url)

      // Planning API (first call)
      if (urlStr.includes('/api/v1/demo/planning-run')) {
        return Promise.resolve(new Response(JSON.stringify({
          success: true,
          summary: { total_area_m2: 850, total_position_count: 300, total_investment_cny: 3000000, total_power_kw: 1350, requires_review: false },
          zone_plan: { result: { zones: [] } },
          investment_estimate: { result: { items: [] } },
          power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false }
        })))
      }

      // Reports list (second call)
      if (urlStr.includes('/api/v1/reports') && !urlStr.includes('/revisions') && !urlStr.includes('/exports')) {
        return Promise.resolve(new Response(JSON.stringify({
          reports: [{ id: 'report-001', status: 'draft' }]
        })))
      }

      // Revisions
      if (urlStr.includes('/revisions')) {
        return Promise.resolve(new Response(JSON.stringify({
          revisions: [{ revision_number: 1, content_hash: 'abc' }]
        })))
      }

      // Exports
      if (urlStr.includes('/exports')) {
        return Promise.resolve(new Response(JSON.stringify({
          exports: [{
            artifact_id: 'art-001',
            status: 'completed',
            format: 'pdf',
            file_name: 'report-001-v1.pdf',
            file_size_bytes: 24576,
            revision_number: 1,
            generated_at: '2026-06-27T12:00:00Z',
            locale: 'zh-CN',
            template_locale: 'zh-CN',
            translation_catalog_version: '1.0',
            translation_catalog_content_hash: 'def',
            localized_template_content_hash: 'ghi'
          }]
        })))
      }

      return Promise.reject(new Error(`unexpected fetch: ${urlStr}`))
    })

    const wrapper = mountApp()
    await flushPromises()
    
    // Submit planning to populate store
    await wrapper.find('.el-button--primary').trigger('click')

    // Wait for the planning API promise + auto-navigation + reports API calls + renders
    await new Promise(resolve => setTimeout(resolve, 50))
    await flushPromises()
    
    // Navigate directly to reports (skip intermediate calculations)
    await testRouter.push('/workbench/reports')
    await new Promise(resolve => setTimeout(resolve, 100))
    await flushPromises()

    // Try to find the report toggle after all the data has loaded
    const reportToggle = wrapper.find('.report-export-panel__toggle')

    // If the toggle doesn't exist (report didn't load), print what's on the page
    if (!reportToggle.exists()) {
      console.log('Page text at time of test failure:', wrapper.text().substring(0, 500))
      // Also check what the mock received:
      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2)
    }

    expect(reportToggle.exists()).toBe(true)
    await reportToggle.trigger('click')
    await new Promise(resolve => setTimeout(resolve, 50))
    await flushPromises()

    // The exports table should now be rendered inside .table-scroll
    const tableScroll = wrapper.find('.table-scroll')
    expect(tableScroll.exists()).toBe(true)
    
    // The table within .table-scroll should contain the artifact data
    const exportTable = wrapper.find('.report-export-panel__exports-table')
    expect(exportTable.exists()).toBe(true)
    expect(exportTable.text()).toContain('report-001-v1.pdf')
    expect(exportTable.text()).toContain('PDF')
    
    // Download button should be accessible
    const downloadBtn = wrapper.find('.report-export-panel__download-btn')
    expect(downloadBtn.exists()).toBe(true)
    expect(downloadBtn.attributes('disabled')).toBeUndefined()
    expect(downloadBtn.text()).toContain('下载')
  })
  
  it('submit and reset buttons visible at 320, 375, and 768', async () => {
    for (const w of [320, 375, 768]) {
      window.innerWidth = w
      window.dispatchEvent(new Event('resize'))
      
      const wrapper = mountApp()
      await flushPromises()
      
      const submitBtn = wrapper.find('.el-button--primary')
      expect(submitBtn.exists()).toBe(true)
      expect(submitBtn.isVisible()).toBe(true)
      
      const resetButton = wrapper.findAll('button').filter(b => b.text().includes('重置'))
      expect(resetButton.length).toBeGreaterThanOrEqual(1)
      expect(resetButton[0].isVisible()).toBe(true)
    }
    window.innerWidth = 1024
  })
  
  it('agent toggle visible and clickable at 320, 375, 768', async () => {
    for (const w of [320, 375, 768]) {
      window.innerWidth = w
      window.dispatchEvent(new Event('resize'))
      
      const wrapper = mountApp()
      await flushPromises()
      
      const toggleBtn = wrapper.find('button.agent-panel__toggle')
      expect(toggleBtn.exists()).toBe(true)
      expect(toggleBtn.isVisible()).toBe(true)
      expect(toggleBtn.attributes('disabled')).toBeUndefined()
      
      // Can open drawer
      await toggleBtn.trigger('click')
      await flushPromises()
      
      const drawer = document.body.querySelector('.agent-panel__drawer')
      expect(drawer).not.toBeNull()
      
      // Close
      const closeBtn = drawer!.querySelector('.agent-panel__close-btn') as HTMLElement | null
      closeBtn?.click()
      await flushPromises()
    }
    window.innerWidth = 1024
  })
  
  it('drawer has width: min(400px, 100vw) CSS contract', async () => {
    window.innerWidth = 320
    window.dispatchEvent(new Event('resize'))

    const wrapper = mountApp()
    await flushPromises()
    await wrapper.find('button.agent-panel__toggle').trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer') as HTMLElement
    expect(drawer).not.toBeNull()

    // CSS contract: read the component source and verify the responsive rule exists.
    // This is a CSS source contract, NOT a browser geometry test.
    const { readFileSync } = await import('fs')
    const { resolve } = await import('path')
    // In vitest's node environment, process.cwd() is the project root
    const source = readFileSync(resolve(process.cwd(), 'src/features/agent/components/AgentPanel.vue'), 'utf-8')
    const normalized = source.replace(/\s+/g, ' ')
    expect(normalized).toMatch(/\.agent-panel__drawer\s*\{[^}]*width:\s*min\(400px,\s*100vw\)/)

    window.innerWidth = 1024
  })
})
