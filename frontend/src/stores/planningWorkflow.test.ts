import { describe, expect, it, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

import { usePlanningWorkflowStore } from './planningWorkflow'

describe('planningWorkflow store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('starts with empty state', () => {
    const store = usePlanningWorkflowStore()
    expect(store.latestRequest).toBeNull()
    expect(store.latestResponse).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.error).toBe('')
  })

  it('execute writes response on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ success: true, summary: { total_area_m2: 850, total_position_count: 300, total_investment_cny: 0, total_power_kw: 0, requires_review: false }, zone_plan: { result: { zones: [] } }, investment_estimate: { result: { items: [] } }, power_configuration: { equipment_rows: [], summary_rows: [], items: [], total_installed_power_kw: 0, total_estimated_demand_kw: 0, requires_review: false } })))
    const store = usePlanningWorkflowStore()
    const result = await store.execute('proj-1', 1, {
      daily_inbound_mass_kg: 100,
      working_time_h_per_day: 8,
      utilization_factor: 0.85,
      reserve_factor: 1.05,
      finished_storage_days: 2,
      packaging_storage_days: 3,
      main_packaging_storage_days: 3,
      auxiliary_packaging_storage_days: 30,
      precooling_required_ratio: 1,
      primary_precooling_working_hours_per_day: 6,
      secondary_precooling_working_hours_per_day: 16,
      raw_storage_ratio: 0.4,
      finished_goods_pallet_weight_kg: 400,
      frozen_fruit_ratio: 0.1,
      frozen_storage_days: 5,
      frozen_goods_pallet_weight_kg: 600
    })
    expect(result).not.toBeNull()
    expect(store.latestResponse).not.toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('execute sets error on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('API error'))
    const store = usePlanningWorkflowStore()
    const result = await store.execute('proj-1', 1, {
      daily_inbound_mass_kg: 100,
      working_time_h_per_day: 8,
      utilization_factor: 0.85,
      reserve_factor: 1.05,
      finished_storage_days: 2,
      packaging_storage_days: 3,
      main_packaging_storage_days: 3,
      auxiliary_packaging_storage_days: 30,
      precooling_required_ratio: 1,
      primary_precooling_working_hours_per_day: 6,
      secondary_precooling_working_hours_per_day: 16,
      raw_storage_ratio: 0.4,
      finished_goods_pallet_weight_kg: 400,
      frozen_fruit_ratio: 0.1,
      frozen_storage_days: 5,
      frozen_goods_pallet_weight_kg: 600
    })
    expect(result).toBeNull()
    expect(store.error).toBe('API error')
    expect(store.isLoading).toBe(false)
  })

  it('cancel clears loading and state', async () => {
    const store = usePlanningWorkflowStore()
    store.cancel()
    expect(store.isLoading).toBe(false)
  })

  it('reset clears everything', async () => {
    const store = usePlanningWorkflowStore()
    store.reset()
    expect(store.latestRequest).toBeNull()
    expect(store.latestResponse).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.error).toBe('')
  })
})
