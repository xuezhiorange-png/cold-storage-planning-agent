import { describe, expect, it, vi } from 'vitest'

import type { PlanningRunRequest, PlanningRunResponse } from '../../../api/contracts/planning'
import type { PlanningApi } from '../api/planningApi'
import { usePlanningRun } from './usePlanningRun'

function createMockResponse(overrides: Partial<PlanningRunResponse> = {}): PlanningRunResponse {
  const summaryDefaults = {
    total_area_m2: 1800,
    total_position_count: 340,
    total_investment_cny: 6_150_000,
    total_power_kw: 1350,
    requires_review: false,
  }
  return {
    success: true,
    summary: {
      ...summaryDefaults,
      ...overrides.summary
    },
    zone_plan: {
      result: {
        zones: overrides.zone_plan?.result?.zones ?? []
      }
    },
    investment_estimate: {
      result: {
        items: overrides.investment_estimate?.result?.items ?? []
      }
    },
    power_configuration: {
      equipment_rows: overrides.power_configuration?.equipment_rows ?? [],
      summary_rows: overrides.power_configuration?.summary_rows ?? [],
      items: overrides.power_configuration?.items ?? [],
      total_installed_power_kw: overrides.power_configuration?.total_installed_power_kw ?? 0,
      total_estimated_demand_kw: overrides.power_configuration?.total_estimated_demand_kw ?? 0,
      requires_review: overrides.power_configuration?.requires_review ?? false
    },
    ...overrides
  }
}

function createMockApi(): PlanningApi {
  return { run: vi.fn() }
}

const exampleRequest: PlanningRunRequest = {
  daily_inbound_mass_kg: 25_000,
  working_time_h_per_day: 16,
  utilization_factor: 0.85,
  finished_storage_days: 2.5,
  packaging_storage_days: 3,
  main_packaging_storage_days: 3,
  auxiliary_packaging_storage_days: 30,
  reserve_factor: 1.05,
  precooling_required_ratio: 1,
  primary_precooling_working_hours_per_day: 6,
  secondary_precooling_working_hours_per_day: 16,
  raw_storage_ratio: 0.4,
  finished_goods_pallet_weight_kg: 400,
  frozen_fruit_ratio: 0.1,
  frozen_storage_days: 5,
  frozen_goods_pallet_weight_kg: 600
}

describe('usePlanningRun', () => {
  it('starts with idle state', () => {
    const api = createMockApi()
    const { data, loading, error } = usePlanningRun(api)

    expect(data.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
  })

  it('returns the response on success and stores it in data', async () => {
    const api = createMockApi()
    const response = createMockResponse({ summary: { total_area_m2: 2000, total_position_count: 0, total_investment_cny: 0, total_power_kw: 0, requires_review: false } })
    vi.mocked(api.run).mockResolvedValue(response)

    const { data, loading, error, execute } = usePlanningRun(api)
    const result = await execute(exampleRequest)

    // Same reference returned directly
    expect(result).toBe(response)
    // Stored as well
    expect(data.value).toStrictEqual(response)
    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
  })

  it('sets loading to true during execution', async () => {
    const api = createMockApi()
    let resolve!: (r: PlanningRunResponse) => void
    vi.mocked(api.run).mockReturnValue(new Promise((r) => { resolve = r }))

    const { execute, loading } = usePlanningRun(api)
    const promise = execute(exampleRequest)

    expect(loading.value).toBe(true)

    resolve(createMockResponse())
    await promise

    expect(loading.value).toBe(false)
  })

  it('captures a non-abort error', async () => {
    const api = createMockApi()
    vi.mocked(api.run).mockRejectedValue(new Error('后端服务不可用'))

    const { data, loading, error, execute } = usePlanningRun(api)
    const result = await execute(exampleRequest)

    expect(result).toBeNull()
    expect(data.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBe('后端服务不可用')
  })

  it('does not update state when request was superseded', async () => {
    const api = createMockApi()
    const responseA = createMockResponse({ summary: { total_area_m2: 1500, total_position_count: 0, total_investment_cny: 0, total_power_kw: 0, requires_review: false } })
    const responseB = createMockResponse({ summary: { total_area_m2: 2500, total_position_count: 0, total_investment_cny: 0, total_power_kw: 0, requires_review: false } })

    vi.mocked(api.run)
      .mockResolvedValueOnce(responseA)
      .mockResolvedValueOnce(responseB)

    const { data, execute } = usePlanningRun(api)

    // Start first request, then start second before it resolves
    const promiseA = execute(exampleRequest)
    const promiseB = execute(exampleRequest)

    await Promise.all([promiseA, promiseB])

    // Only the latest result should be stored
    expect(data.value).toEqual(responseB)
  })

  it('aborts the active request', async () => {
    const api = createMockApi()
    vi.mocked(api.run).mockImplementation(
      (_, signal) =>
        new Promise((_, reject) => {
          signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'))
          })
        })
    )

    const { data, loading, error, execute, abort } = usePlanningRun(api)
    const promise = execute(exampleRequest)

    abort()

    await promise
    expect(data.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
  })

  it('reset clears all state', async () => {
    const api = createMockApi()
    vi.mocked(api.run).mockResolvedValue(createMockResponse())

    const { data, loading, error, execute, reset } = usePlanningRun(api)
    await execute(exampleRequest)

    expect(data.value).not.toBeNull()

    reset()

    expect(data.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
  })
})
