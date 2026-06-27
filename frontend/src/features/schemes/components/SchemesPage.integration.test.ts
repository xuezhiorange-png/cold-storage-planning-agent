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

  it('stale A success does not overwrite B success — A pending, B supersedes', async () => {
    // Start in success state with scheme A
    mockFetchResolve(successResp([schemeA], 'A'))
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    // Click refresh: A is deferred (pending)
    let resolveA: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => new Promise<Response>(resolve => { resolveA = resolve })
    )
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()
    // A is pending — refresh button now shows "重新加载"
    expect(wrapper.text()).toContain('加载方案数据')


    // While A is pending, click "重新加载" to start B
    let resolveB: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => new Promise<Response>(resolve => { resolveB = resolve })
    )
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    // B resolves first with scheme B
    resolveB!(new Response(JSON.stringify(successResp([schemeB], 'B'))))
    await flushPromises()
    expect(wrapper.text()).toContain('方案B')
    expect(wrapper.text()).not.toContain('方案A')

    // A resolves after B — should NOT overwrite B
    resolveA!(new Response(JSON.stringify(successResp([schemeA], 'A'))))
    await flushPromises()
    expect(wrapper.text()).toContain('方案B')
    expect(wrapper.text()).not.toContain('方案A')
    expect(wrapper.find('.schemes-page__error').exists()).toBe(false)
  })

  it('stale A error does not clear B success — A pending, B supersedes', async () => {
    // Start in success state with scheme A
    mockFetchResolve(successResp([schemeA], 'A'))
    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('方案A')

    // Click refresh: A is deferred
    let resolveA: ((v: Response) => void) | null = null
    let rejectA: ((e: Error) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => new Promise<Response>((resolve, reject) => { resolveA = resolve; rejectA = reject })
    )
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('加载方案数据')

    // While A is pending, click "重新加载" to start B
    let resolveB: ((v: Response) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => new Promise<Response>(resolve => { resolveB = resolve })
    )
    await wrapper.find('.schemes-page__refresh').trigger('click')
    await flushPromises()

    // B resolves first with scheme B
    resolveB!(new Response(JSON.stringify(successResp([schemeB], 'B'))))
    await flushPromises()
    expect(wrapper.text()).toContain('方案B')

    // A rejects after B — should NOT clear B's data or show error
    rejectA!(new Error('stale A failure'))
    await flushPromises()
    expect(wrapper.text()).toContain('方案B')
    expect(wrapper.text()).not.toContain('方案A')
    expect(wrapper.find('.schemes-page__error').exists()).toBe(false)
  })
})

describe('SchemesPage unmount', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('unmount during pending request cancels and prevents stale update', async () => {
    let resolveFetch: ((v: Response) => void) | null = null
    let rejectFetch: ((e: Error) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => new Promise<Response>((resolve, reject) => { resolveFetch = resolve; rejectFetch = reject })
    )

    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()

    wrapper.unmount()
    await flushPromises()

    // Resolve after unmount — should not produce warning or error
    resolveFetch!(new Response(JSON.stringify(successResp([schemeA], 'A'))))
    await flushPromises()

    // No unhandled rejection, no "state update after unmount" warning
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('unmount during pending request prevents stale error', async () => {
    let rejectFetch: ((e: Error) => void) | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => new Promise<Response>((_resolve, reject) => { rejectFetch = reject })
    )

    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const wrapper = mount(SchemesPage, { global: { plugins: [router] } })
    await flushPromises()

    wrapper.unmount()
    await flushPromises()

    // Reject after unmount
    rejectFetch!(new Error('Network error'))
    await flushPromises()

    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
