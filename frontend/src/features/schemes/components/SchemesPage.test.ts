import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import SchemesPage from './SchemesPage.vue'
import { mockSchemeRunFetch, setupSchemesPagePinia } from '../../../../tests/helpers/schemesPageTestHelpers'

const schemeA = {
  scheme_code: 'A',
  scheme_name: '方案A',
  feasible: true,
  total_score: '95',
  total_area_m2: 1000,
  total_position_count: 200,
  room_module_count: 8,
  door_count: 16,
  investment_cny: 5000000,
  installed_power_kw_e: 800,
  requires_review: false
}
const schemeB = {
  scheme_code: 'B',
  scheme_name: '方案B',
  feasible: false,
  total_score: '78',
  total_area_m2: 1200,
  total_position_count: 180,
  room_module_count: 6,
  door_count: 12,
  investment_cny: 4500000,
  installed_power_kw_e: 750,
  requires_review: true
}

describe('SchemesPage state transitions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  function mountPage() {
    const pinia = setupSchemesPagePinia()
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', name: 'schemes', component: SchemesPage }]
    })
    return mount(SchemesPage, { global: { plugins: [router, pinia] } })
  }

  it('success -> error clears old cards', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    mockSchemeRunFetch(fetchMock, [schemeA], 'A')
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('A')

    fetchMock.mockRejectedValueOnce(new Error('Network down'))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('推荐')
  })

  it('success -> unavailable clears old cards', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    mockSchemeRunFetch(fetchMock, [schemeA], 'A')
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('A')

    fetchMock.mockResolvedValueOnce(new Response('Not Found', { status: 404 }))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('方案比选服务当前不可用')
  })

  it('success -> empty clears old cards', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    mockSchemeRunFetch(fetchMock, [schemeA], 'A')
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('A')

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([])))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('暂无方案数据')
  })

  it('error -> retry -> success', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockRejectedValueOnce(new Error('Network down'))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)

    mockSchemeRunFetch(fetchMock, [schemeB], null)
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('.schemes-page__error').exists()).toBe(false)
    expect(wrapper.text()).toContain('B')
    expect(wrapper.text()).toContain('暂无推荐方案')
  })

  it('unavailable -> retry -> success', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockResolvedValueOnce(new Response('Not Found', { status: 404 }))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('方案比选服务当前不可用')

    mockSchemeRunFetch(fetchMock, [schemeA], 'A')
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('.schemes-page__unavailable').exists()).toBe(false)
    expect(wrapper.text()).toContain('A')
    expect(wrapper.text()).toContain('推荐')
  })
})
