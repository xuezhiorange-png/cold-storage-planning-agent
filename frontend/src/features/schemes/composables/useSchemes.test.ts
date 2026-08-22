import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

import type { HttpClient } from '../../../api/httpClient'
import { ApiError } from '../../../api/errors'
import { createSchemesApi, type SchemesApi } from '../api/schemesApi'
import { useSchemes, type SchemesState, type UseSchemesReturn } from './useSchemes'

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

function createClient(): HttpClient {
  return {
    requestJson: vi.fn(),
    requestBlob: vi.fn(),
    requestBinary: vi.fn()
  }
}

function createMockApi(client: HttpClient): SchemesApi {
  return createSchemesApi(client)
}

function makeSchemes(count: number): Array<Record<string, unknown>> {
  const items: Array<Record<string, unknown>> = []
  for (let i = 1; i <= count; i++) {
    items.push({
      scheme_code: `S${i}`,
      scheme_name: `方案 ${i}`,
      feasible: true,
      total_score: `${95 - i * 5}`,
      total_area_m2: 1000 + i * 200,
      total_position_count: 50 + i * 10,
      room_module_count: 20 + i,
      door_count: 10 + i,
      investment_cny: 500000 + i * 100000,
      installed_power_kw_e: 100 + i * 20,
      requires_review: false
    })
  }
  return items
}

function makeResponse(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    schemes: makeSchemes(2),
    recommended_scheme_code: 'S1',
    weight_set_name: '项目持久化方案比选',
    weight_set_status: 'persisted',
    ...overrides
  }
}

const PROJECT_ID = 'proj-1'
const VERSION = 1

function makeRunDetail(schemes: Array<Record<string, unknown>> = makeSchemes(2)) {
  return {
    run_id: 'run-1',
    recommended_scheme_code: (schemes[0]?.scheme_code as string) ?? 'S1',
    requires_review: false,
    candidates: schemes.map((scheme, index) => ({
      scheme_code: scheme.scheme_code,
      feasible: scheme.feasible,
      rank: index + 1,
      total_score: scheme.total_score,
      result_snapshot: {
        total_area_m2: scheme.total_area_m2,
        total_position_count: scheme.total_position_count,
        room_module_count: scheme.room_module_count,
        door_count: scheme.door_count,
        investment_cny: scheme.investment_cny,
        installed_power_kw_e: scheme.installed_power_kw_e,
        requires_review: scheme.requires_review
      },
      constraint_results: []
    }))
  }
}

function mockListAndDetail(c: HttpClient, schemes: Array<Record<string, unknown>> = makeSchemes(2)) {
  if (schemes.length === 0) {
    vi.mocked(c.requestJson).mockResolvedValueOnce([])
    return
  }
  vi.mocked(c.requestJson)
    .mockResolvedValueOnce([{ run_id: 'run-1', status: 'completed' }])
    .mockResolvedValueOnce(makeRunDetail(schemes))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useSchemes', () => {
  /* ── Initial state ─────────────────────────────────────────── */

  it('starts with idle state', () => {
    const c = createClient()
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    expect(ctx.data.value).toBeNull()
    expect(ctx.schemes.value).toEqual([])
    expect(ctx.state.value).toBe('idle' satisfies SchemesState)
    expect(ctx.error.value).toBe('')
  })

  /* ── Loading state ─────────────────────────────────────────── */

  it('enters loading state when load() is called', async () => {
    const c = createClient()
    const api = createMockApi(c)

    let resolveList!: (v: unknown) => void
    vi.mocked(c.requestJson)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve }))
      .mockResolvedValueOnce(makeRunDetail())

    const ctx = useSchemes(api)

    const loadPromise = ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('loading' satisfies SchemesState)
    expect(ctx.error.value).toBe('')

    resolveList([{ run_id: 'run-1', status: 'completed' }])
    await loadPromise
  })

  /* ── Success state ─────────────────────────────────────────── */

  it('transitions to success after loading completes', async () => {
    const c = createClient()
    mockListAndDetail(c)
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('success' satisfies SchemesState)
    expect(ctx.data.value).not.toBeNull()
    expect(ctx.data.value?.schemes).toHaveLength(2)
    expect(ctx.data.value?.recommended_scheme_code).toBe('S1')
    expect(ctx.data.value?.weight_set_name).toBe('项目持久化方案比选')
    expect(ctx.data.value?.weight_set_status).toBe('persisted')
    expect(ctx.error.value).toBe('')
  })

  it('populates schemes computed from response', async () => {
    const c = createClient()
    mockListAndDetail(c)
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.schemes.value).toHaveLength(2)
    expect(ctx.schemes.value[0].scheme_code).toBe('S1')
    expect(ctx.schemes.value[1].scheme_name).toBe('S2')
  })

  /* ── Empty state ───────────────────────────────────────────── */

  it('transitions to empty when response has zero schemes', async () => {
    const c = createClient()
    mockListAndDetail(c, [])
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('empty' satisfies SchemesState)
    expect(ctx.data.value?.schemes).toEqual([])
    expect(ctx.schemes.value).toEqual([])
  })

  /* ── Error state ───────────────────────────────────────────── */

  it('transitions to error on API failure', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(new Error('Network error'))
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('error' satisfies SchemesState)
    expect(ctx.error.value).toBe('Network error')
    expect(ctx.data.value).toBeNull()
    expect(ctx.schemes.value).toEqual([])
  })

  it('captures error message from non-AbortError exceptions', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(new Error('超时'))
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('error' satisfies SchemesState)
    expect(ctx.error.value).toBe('超时')
  })

  /* ── Abort handling ────────────────────────────────────────── */

  it('ignores AbortError and preserves previous state', async () => {
    const c = createClient()
    const api = createMockApi(c)

    // First load succeeds
    mockListAndDetail(c)
    const ctx = useSchemes(api)
    await ctx.load(PROJECT_ID, VERSION)
    expect(ctx.state.value).toBe('success')

    // Second load is aborted
    vi.mocked(c.requestJson).mockRejectedValueOnce(
      new DOMException('The operation was aborted', 'AbortError')
    )
    await ctx.load(PROJECT_ID, VERSION)

    // State should remain as 'success' from the first load
    expect(ctx.state.value).toBe('success')
    expect(ctx.data.value?.schemes).toHaveLength(2)
  })

  /* ── Stale response protection ─────────────────────────────── */

  it('discards stale responses from earlier load calls', async () => {
    const c = createClient()
    const api = createMockApi(c)

    let resolveFirst!: (v: unknown) => void
    const firstPromise = new Promise((resolve) => {
      resolveFirst = resolve
    })

    vi.mocked(c.requestJson)
      .mockImplementationOnce(() => firstPromise)
      .mockResolvedValueOnce([{ run_id: 'run-1', status: 'completed' }])
      .mockResolvedValueOnce(
        makeRunDetail(
          makeSchemes(2).map((scheme, index) => ({
            ...scheme,
            scheme_code: index === 0 ? 'S2' : scheme.scheme_code
          }))
        )
      )

    const ctx = useSchemes(api)

    // Start first load
    const firstLoad = ctx.load(PROJECT_ID, VERSION)

    // Start second load (aborts first via gate)
    await ctx.load(PROJECT_ID, VERSION)

    // Resolve first (stale) response — list only
    resolveFirst([{ run_id: 'run-1', status: 'completed' }])
    await firstLoad

    // Data should be from the second (current) load
    expect(ctx.data.value?.recommended_scheme_code).toBe('S2')
    expect(ctx.state.value).toBe('success' satisfies SchemesState)
  })

  /* ── abort ─────────────────────────────────────────────────── */

  it('abort() cancels in-flight request and resets state to idle', async () => {
    const c = createClient()
    const api = createMockApi(c)

    let resolveList!: (v: unknown) => void
    vi.mocked(c.requestJson)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve }))
      .mockResolvedValueOnce(makeRunDetail())

    const ctx = useSchemes(api)

    const loadPromise = ctx.load(PROJECT_ID, VERSION)
    expect(ctx.state.value).toBe('loading')

    ctx.abort()
    expect(ctx.state.value).toBe('idle' satisfies SchemesState)

    resolveList([{ run_id: 'run-1', status: 'completed' }])
    await loadPromise

    expect(ctx.state.value).toBe('idle' satisfies SchemesState)
    expect(ctx.data.value).toBeNull()
  })

  /* ── Component unmount cancellation ────────────────────── */

  it('does not update state after abort() is called', async () => {
    const c = createClient()
    const api = createMockApi(c)

    let resolveList!: (v: unknown) => void
    vi.mocked(c.requestJson)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve }))
      .mockResolvedValueOnce(makeRunDetail())

    const ctx = useSchemes(api)

    const loadPromise = ctx.load(PROJECT_ID, VERSION)
    expect(ctx.state.value).toBe('loading')

    ctx.abort()

    resolveList([{ run_id: 'run-1', status: 'completed' }])
    await loadPromise

    expect(ctx.state.value).toBe('idle' satisfies SchemesState)
    expect(ctx.data.value).toBeNull()
  })

  it('does not update state after component is unmounted', async () => {
    const c = createClient()
    const api = createMockApi(c)

    let resolveList!: (v: unknown) => void
    vi.mocked(c.requestJson)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve }))
      .mockResolvedValueOnce(makeRunDetail())

    const TestComponent = defineComponent({
      setup() {
        const ctx = useSchemes(api)
        ;(window as unknown as Record<string, unknown>).__ctx = ctx
        ctx.load(PROJECT_ID, VERSION)
        return () => h('div', 'test')
      }
    })

    const wrapper = mount(TestComponent, {
      global: {
        plugins: []
      }
    })
    await flushPromises()

    const ctx = (window as unknown as Record<string, unknown>).__ctx as UseSchemesReturn
    expect(ctx.state.value).toBe('loading')

    wrapper.unmount()

    resolveList([{ run_id: 'run-1', status: 'completed' }])
    await flushPromises()

    expect(ctx.state.value).toBe('idle' satisfies SchemesState)
    expect(ctx.data.value).toBeNull()

    delete (window as unknown as Record<string, unknown>).__ctx
  })

  /* ── Unavailable state ───────────────────────────────────────── */

  it('transitions to unavailable on 404 ApiError', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(
      new ApiError({ status: 404, message: 'Not found' })
    )
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('unavailable' satisfies SchemesState)
    expect(ctx.error.value).toBe('方案比选服务当前不可用')
    expect(ctx.data.value).toBeNull()
  })

  it('transitions to unavailable on 501 ApiError', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(
      new ApiError({ status: 501, message: 'Not implemented' })
    )
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('unavailable' satisfies SchemesState)
    expect(ctx.error.value).toBe('方案比选服务当前不可用')
  })

  it('transitions to unavailable on FEATURE_DISABLED ApiError', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(
      new ApiError({ status: 403, message: 'Feature disabled', code: 'FEATURE_DISABLED' })
    )
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('unavailable' satisfies SchemesState)
    expect(ctx.error.value).toBe('方案比选服务当前不可用')
  })

  it('transitions to error on other ApiError status', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(
      new ApiError({ status: 500, message: 'Internal server error' })
    )
    const api = createMockApi(c)
    const ctx = useSchemes(api)

    await ctx.load(PROJECT_ID, VERSION)

    expect(ctx.state.value).toBe('error' satisfies SchemesState)
    expect(ctx.error.value).toBe('Internal server error')
  })
})
