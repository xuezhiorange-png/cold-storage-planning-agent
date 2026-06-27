import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { createRouter } from 'vue-router'

import SchemesPage from './SchemesPage.vue'

function mockSchemeData(schemes: any[] = [], recommended: string | null = null) {
  return {
    schemes,
    recommended_scheme_code: recommended,
    weight_set_name: '默认权重集',
    weight_set_status: 'verified'
  }
}

const schemeA = { scheme_code: 'A', scheme_name: '方案A', feasible: true, total_score: '95', total_area_m2: 1000, total_position_count: 200, room_module_count: 8, door_count: 16, investment_cny: 5000000, installed_power_kw_e: 800, requires_review: false }
const schemeB = { scheme_code: 'B', scheme_name: '方案B', feasible: false, total_score: '78', total_area_m2: 1200, total_position_count: 180, room_module_count: 6, door_count: 12, investment_cny: 4500000, installed_power_kw_e: 750, requires_review: true }

describe('SchemesPage state transitions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  function mountPage() {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', name: 'schemes', component: SchemesPage }] })
    return mount(SchemesPage, { global: { plugins: [router] } })
  }

  // ── State transitions ──

  it('success -> error clears old cards', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(mockSchemeData([schemeA], 'A'))))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    // Second call: error
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network down'))
    // Trigger refresh
    const refreshBtn = wrapper.find('.schemes-page__refresh')
    expect(refreshBtn.exists()).toBe(true)
    await refreshBtn.trigger('click')
    await flushPromises()

    // Cards gone, error shown
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('方案A')
  })

  it('success -> unavailable clears old cards', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(mockSchemeData([schemeA], 'A'))))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('Not Found', { status: 404 }))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('方案比选服务当前不可用')
    expect(wrapper.text()).not.toContain('方案A')
  })

  it('success -> empty clears old cards', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(mockSchemeData([schemeA], 'A'))))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(mockSchemeData([]))))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('暂无方案数据')
    expect(wrapper.text()).not.toContain('方案A')
  })

  it('error -> retry -> success', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network down'))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(mockSchemeData([schemeB], null))))
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('.schemes-page__error').exists()).toBe(false)
    expect(wrapper.text()).toContain('方案B')
    expect(wrapper.text()).toContain('暂无推荐方案')
  })

  it('unavailable -> retry -> success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('Not Found', { status: 404 }))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('方案比选服务当前不可用')
    expect(wrapper.find('.schemes-page__retry').exists()).toBe(true)

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(mockSchemeData([schemeA], 'A'))))
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('.schemes-page__unavailable').exists()).toBe(false)
    expect(wrapper.text()).toContain('方案A')
    expect(wrapper.text()).toContain('推荐')
  })
})
