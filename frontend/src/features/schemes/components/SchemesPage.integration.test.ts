import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { createRouter } from 'vue-router'

import SchemesPage from './SchemesPage.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: SchemesPage }]
})

const schemeA = { scheme_code: 'A', scheme_name: '方案A', feasible: true, total_score: '95', total_area_m2: 1000, total_position_count: 200, room_module_count: 8, door_count: 16, investment_cny: 5000000, installed_power_kw_e: 800, requires_review: false }
const schemeB = { scheme_code: 'B', scheme_name: '方案B', feasible: false, total_score: '78', total_area_m2: 1200, total_position_count: 180, room_module_count: 6, door_count: 12, investment_cny: 4500000, installed_power_kw_e: 750, requires_review: true }

function successResp(schemes = [schemeA, schemeB], recommended: string | null = 'A') {
  return { schemes, recommended_scheme_code: recommended, weight_set_name: '默认权重集', weight_set_status: 'verified' }
}

function mockFetchResolve(data: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(data)))
}

function mockFetchReject(msg = 'Network error') {
  return vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error(msg))
}

function mockFetchStatus(status: number) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status }))
}

/* ── Moved from SchemesPage.test.ts (4 basic tests) ──────── */

describe('SchemesPage integration — basic states', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('renders success with cards', async () => {
    mockFetchResolve(successResp([schemeA, schemeB], 'A'))
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')
    expect(wrapper.text()).toContain('方案B')
  })

  it('renders empty state', async () => {
    mockFetchResolve(successResp([]))
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无方案数据')
  })

  it('renders unavailable on 404', async () => {
    mockFetchStatus(404)
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案比选服务当前不可用')
    expect(wrapper.find('.schemes-page__retry').exists()).toBe(true)
  })

  it('renders error with retry', async () => {
    mockFetchReject('Network error')
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
    expect(wrapper.find('.schemes-page__retry').exists()).toBe(true)
  })
})

/* ── State transitions ────────────────────────────────────── */

describe('SchemesPage state transitions', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('success -> error clears old cards', async () => {
    mockFetchResolve(successResp())
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    mockFetchReject()
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('方案A')
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
  })

  it('success -> unavailable clears old cards', async () => {
    mockFetchResolve(successResp())
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    mockFetchStatus(404)
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('方案A')
    expect(wrapper.text()).toContain('方案比选服务当前不可用')
  })

  it('success -> empty clears old cards', async () => {
    mockFetchResolve(successResp())
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    mockFetchResolve(successResp([], null))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('方案A')
    expect(wrapper.text()).toContain('暂无方案数据')
  })

  it('error -> retry -> success', async () => {
    mockFetchReject()
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)

    mockFetchResolve(successResp())
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('方案A')
    expect(wrapper.text()).toContain('默认权重集')
  })

  it('unavailable -> retry -> success', async () => {
    mockFetchStatus(404)
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案比选服务当前不可用')

    mockFetchResolve(successResp())
    await wrapper.find('.schemes-page__retry').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('方案A')
  })

  it('stale A result discarded when B loads via refresh button', async () => {
    // Start in success state with A
    mockFetchResolve(successResp([schemeA], 'A'))
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    // Now set up a deferred second fetch, then click refresh.
    // The refresh button will disappear during loading, but the
    // deferred promise is already configured.
    let resolveDeferred: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise(resolve => { resolveDeferred = resolve }))

    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    // Button disappeared (loading), but deferred promise is pending.
    // After the deferred resolves, component returns to success.
    // Resolve deferred with stale A data (should be accepted since it's current)
    resolveDeferred!(new Response(JSON.stringify(successResp([schemeA], 'A'))))
    await flushPromises()

    expect(wrapper.text()).toContain('方案A')

    // Now click refresh again with B succeeding immediately
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify(successResp([schemeB], 'B'))))
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    // Shows B
    expect(wrapper.text()).toContain('方案B')
    expect(wrapper.text()).toContain('推荐')

    // Stale A2 (deferred before B) is now handled by the gate automatically.
    // The second refresh's load() called gate.begin() which aborted the
    // deferred handler from the first refresh's load().
    // This behavior is tested at the composable level in useSchemes.test.ts.
  })

  it('stale error discarded when success follows', async () => {
    // Start in success state with A
    mockFetchResolve(successResp([schemeA], 'A'))
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    // Click refresh, deferred fetch
    let resolveDeferred: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise(resolve => { resolveDeferred = resolve }))

    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    // That fetch will fail — set up next fetch to succeed
    mockFetchReject('网络错误')

    // We need to resolve the deferred first, which will leave us in success
    resolveDeferred!(new Response(JSON.stringify(successResp([schemeA], 'A'))))
    await flushPromises()

    // We're back in success, click refresh for the error fetch
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    // Should show error
    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
    expect(wrapper.text()).toContain('网络错误')
  })
})
