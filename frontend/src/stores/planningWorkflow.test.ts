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
    const result = await store.execute({ daily_inbound_mass_kg: 100, working_time_h_per_day: 8 } as any)
    expect(result).not.toBeNull()
    expect(store.latestResponse).not.toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('execute sets error on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('API error'))
    const store = usePlanningWorkflowStore()
    const result = await store.execute({ daily_inbound_mass_kg: 100, working_time_h_per_day: 8 } as any)
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
