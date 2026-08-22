import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import SchemesPage from './SchemesPage.vue'
import { mockSchemeRunFetch, setupSchemesPagePinia } from '../../../../tests/helpers/schemesPageTestHelpers'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: SchemesPage }]
})

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

function mountPage() {
  const pinia = setupSchemesPagePinia()
  return mount(SchemesPage, { global: { plugins: [router, pinia] } })
}

describe('SchemesPage integration — basic states', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders success with cards', async () => {
    mockSchemeRunFetch(vi.spyOn(globalThis, 'fetch'), [schemeA, schemeB], 'A')
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('A')
    expect(wrapper.text()).toContain('B')
  })

  it('renders empty state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify([])))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('暂无方案数据')
  })

  it('renders unavailable on 404', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('Not Found', { status: 404 }))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('方案比选服务当前不可用')
    expect(wrapper.find('.schemes-page__retry').exists()).toBe(true)
  })

  it('renders error with retry', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
    expect(wrapper.find('.schemes-page__retry').exists()).toBe(true)
  })
})

describe('SchemesPage integration — consumer behavior', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('error -> retry -> success uses persisted scheme-runs API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockRejectedValueOnce(new Error('Network error'))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)

    mockSchemeRunFetch(fetchMock, [schemeA], 'A')
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('A')
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/scheme-runs'))).toBe(true)
  })
})
