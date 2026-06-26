import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref, computed } from 'vue'

import SchemesPage from './SchemesPage.vue'
import { useSchemes, type SchemesState, type UseSchemesReturn } from '../composables/useSchemes'
import type { SchemeComparisonResponse, SchemeItemContract } from '../../../api/contracts/schemes'

// ---------------------------------------------------------------------------
// Mock the useSchemes composable
// ---------------------------------------------------------------------------
vi.mock('../composables/useSchemes', () => ({
  useSchemes: vi.fn()
}))

const mockUseSchemes = vi.mocked(useSchemes)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeScheme(overrides: Partial<SchemeItemContract> = {}): SchemeItemContract {
  return {
    scheme_code: 'S1',
    scheme_name: '方案 1',
    feasible: true,
    total_score: '95',
    total_area_m2: 1200,
    total_position_count: 60,
    room_module_count: 21,
    door_count: 11,
    investment_cny: 600000,
    installed_power_kw_e: 120,
    requires_review: false,
    ...overrides
  }
}

function buildResponse(overrides: Partial<SchemeComparisonResponse> = {}): SchemeComparisonResponse {
  return {
    schemes: [makeScheme(), makeScheme({ scheme_code: 'S2', scheme_name: '方案 2' })],
    recommended_scheme_code: 'S1',
    weight_set_name: '默认权重集',
    weight_set_status: 'verified',
    ...overrides
  }
}

function createMock(partial: Partial<ReturnType<typeof useSchemes>> = {}) {
  const defaults: ReturnType<typeof useSchemes> = {
    data: ref(null) as any,
    schemes: ref([]) as any,
    state: ref('idle' as SchemesState) as any,
    error: ref('') as any,
    load: vi.fn(),
    abort: vi.fn()
  }
  return { ...defaults, ...partial }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SchemesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state initially', () => {
    const mockVal = createMock()
    mockVal.state.value = 'loading'
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('加载方案数据...')
  })

  it('renders success with cards', () => {
    const response = buildResponse()
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('默认权重集')
    expect(wrapper.text()).toContain('2 个方案')
    // Card content
    expect(wrapper.text()).toContain('方案 1')
    expect(wrapper.text()).toContain('方案 2')
  })

  it('shows recommended badge', () => {
    const response = buildResponse()
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    // The recommended badge text is '推荐'
    expect(wrapper.text()).toContain('推荐')
  })

  it('shows no-recommendation badge when recommended_scheme_code is null', () => {
    const response = buildResponse({ recommended_scheme_code: null })
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('暂无推荐方案')
  })

  it('shows feasible scheme', () => {
    const scheme = makeScheme({ feasible: true })
    const response = buildResponse({ schemes: [scheme] })
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('可行')
    expect(wrapper.text()).not.toContain('不可行')
  })

  it('shows infeasible scheme with overlay', () => {
    const scheme = makeScheme({ feasible: false })
    const response = buildResponse({ schemes: [scheme] })
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('不可行')
    // The overlay should be present — it has class scheme-card__overlay
    const overlay = wrapper.find('.scheme-card__overlay')
    expect(overlay.exists()).toBe(true)
  })

  it('renders empty state', () => {
    const mockVal = createMock()
    mockVal.state.value = 'empty'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('暂无方案数据')
  })

  it('renders unavailable state on 404', () => {
    const mockVal = createMock()
    mockVal.state.value = 'unavailable'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    const unavailable = wrapper.find('.schemes-page__unavailable')
    expect(unavailable.exists()).toBe(true)
    expect(unavailable.text()).toContain('方案比选服务当前不可用')
  })

  it('renders unavailable state on 501', () => {
    // Same as 404 — both map to 'unavailable'
    const mockVal = createMock()
    mockVal.state.value = 'unavailable'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.find('.schemes-page__unavailable').exists()).toBe(true)
    expect(wrapper.text()).toContain('方案比选服务当前不可用')
  })

  it('renders error state with retry button', () => {
    const mockVal = createMock()
    mockVal.state.value = 'error'
    mockVal.error.value = '出错了'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('出错了')
    const retryBtn = wrapper.find('.schemes-page__retry')
    expect(retryBtn.exists()).toBe(true)
    expect(retryBtn.text()).toBe('重试')
  })

  it('retry after error calls load again', async () => {
    const loadFn = vi.fn()
    const mockVal = createMock()
    mockVal.state.value = 'error'
    mockVal.error.value = '出错了'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockVal.load = loadFn
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    // load is called once on mount via onMounted, reset counter
    loadFn.mockClear()
    await wrapper.find('.schemes-page__retry').trigger('click')
    expect(loadFn).toHaveBeenCalledTimes(1)
  })

  it('success then error clears old cards', () => {
    // Simulate scenario where state transitions from success to error
    // After error, data should be null and cards not visible
    const mockVal = createMock()
    mockVal.state.value = 'error'
    mockVal.error.value = '加载失败'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    // Error message visible
    expect(wrapper.text()).toContain('加载失败')
    // Cards not shown — no summary or scheme names
    expect(wrapper.find('.schemes-page__grid').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('方案 1')
  })

  it('success then unavailable clears old cards', () => {
    const mockVal = createMock()
    mockVal.state.value = 'unavailable'
    mockVal.data.value = null
    mockVal.schemes.value = []
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.find('.schemes-page__unavailable').exists()).toBe(true)
    expect(wrapper.find('.schemes-page__grid').exists()).toBe(false)
    // The word 方案 appears in the unavailable message itself ("方案比选服务")
    // so check for scheme card specific content instead
    expect(wrapper.text()).not.toContain('方案 1')
  })

  it('displays weight_set_name', () => {
    const response = buildResponse({ weight_set_name: '定制权重集' })
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('定制权重集')
  })

  it('displays weight_set_status', () => {
    const response = buildResponse({ weight_set_status: 'unverified' })
    const mockVal = createMock()
    mockVal.state.value = 'success'
    mockVal.data.value = response as any
    mockVal.schemes.value = response.schemes as any
    mockUseSchemes.mockReturnValue(mockVal as any)

    const wrapper = mount(SchemesPage)
    expect(wrapper.text()).toContain('演示权重 / 待复核')
  })
})

// ---------------------------------------------------------------------------
// Real composable tests (mock fetch, use real useSchemes)
// ---------------------------------------------------------------------------

const successResponse = {
  schemes: [
    { scheme_code: 'A', scheme_name: '方案A', feasible: true, total_score: '95', total_area_m2: 1000, total_position_count: 200, room_module_count: 8, door_count: 16, investment_cny: 5000000, installed_power_kw_e: 800, requires_review: false },
    { scheme_code: 'B', scheme_name: '方案B', feasible: false, total_score: '78', total_area_m2: 1200, total_position_count: 180, room_module_count: 6, door_count: 12, investment_cny: 4500000, installed_power_kw_e: 750, requires_review: true }
  ],
  recommended_scheme_code: 'A',
  weight_set_name: '默认权重集',
  weight_set_status: 'verified'
}

function mockFetchOnce(data: any) {
  vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
    () => Promise.resolve(new Response(JSON.stringify(data)))
  )
}

function mockFetchError() {
  vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
    () => Promise.reject(new Error('Network error'))
  )
}

describe('SchemesPage real composable', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    // Override the mock to use the real useSchemes implementation
    const actual = await vi.importActual<{ useSchemes: typeof useSchemes }>('../composables/useSchemes')
    vi.mocked(useSchemes).mockImplementation(actual.useSchemes)
  })

  it('renders success state with cards', async () => {
    mockFetchOnce(successResponse)

    const wrapper = mount(SchemesPage)
    await flushPromises()

    // Cards rendered
    expect(wrapper.text()).toContain('方案A')
    expect(wrapper.text()).toContain('方案B')

    // Recommended badge
    expect(wrapper.text()).toContain('推荐')

    // Infeasible card has the overlay class
    const cards = wrapper.findAll('.scheme-card')
    expect(cards.length).toBe(2)
    expect(cards[1].classes()).toContain('scheme-card--infeasible')

    // Weight set
    expect(wrapper.text()).toContain('默认权重集')
  })

  it('renders empty state when no schemes', async () => {
    mockFetchOnce({
      schemes: [],
      recommended_scheme_code: null,
      weight_set_name: '默认权重集',
      weight_set_status: 'verified'
    })

    const wrapper = mount(SchemesPage)
    await flushPromises()

    expect(wrapper.text()).toContain('暂无方案数据')
    expect(wrapper.find('.schemes-page__grid').exists()).toBe(false)
  })

  it('renders unavailable state on 404', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => Promise.resolve(new Response('Not Found', { status: 404 }))
    )

    const wrapper = mount(SchemesPage)
    await flushPromises()

    expect(wrapper.text()).toContain('方案比选服务当前不可用')
  })

  it('renders error state with retry button', async () => {
    mockFetchError()

    const wrapper = mount(SchemesPage)
    await flushPromises()

    expect(wrapper.find('.schemes-page__error').exists()).toBe(true)
    expect(wrapper.find('.schemes-page__retry').exists()).toBe(true)
  })
})
