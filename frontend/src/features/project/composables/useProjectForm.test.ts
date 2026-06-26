import { describe, expect, it, vi } from 'vitest'

import { createDefaultDesignInputs } from '../model/designInputs'
import type { PlanningRunResponse } from '../../../api/contracts/planning'
import {
  useProjectForm,
  createDefaultFactoryOverview,
  type FactoryOverview
} from './useProjectForm'

function mockApi() {
  return {
    run: vi.fn()
  }
}

describe('useProjectForm', () => {
  describe('createDefaultFactoryOverview', () => {
    it('returns the default factory overview values', () => {
      const overview = createDefaultFactoryOverview()
      expect(overview).toEqual<FactoryOverview>({
        factoryName: '蓝莓加工厂',
        plantingAreaMu: 1250,
        mainVarieties: '蓝莓'
      })
    })
  })

  describe('initial state', () => {
    it('starts with default design inputs', () => {
      const { designInputs } = useProjectForm(mockApi())
      expect({ ...designInputs }).toEqual(createDefaultDesignInputs())
    })

    it('starts with default factory overview', () => {
      const { factoryOverview } = useProjectForm(mockApi())
      expect({ ...factoryOverview }).toEqual(createDefaultFactoryOverview())
    })

    it('starts empty submitting, submitError, and validationErrors', () => {
      const { submitting, submitError, validationErrors } = useProjectForm(mockApi())
      expect(submitting.value).toBe(false)
      expect(submitError.value).toBe('')
      expect(validationErrors.value).toEqual([])
    })
  })

  describe('validate()', () => {
    it('returns true when all inputs are valid', () => {
      const { validate } = useProjectForm(mockApi())
      expect(validate()).toBe(true)
    })

    it('returns false and populates validationErrors for invalid inputs', () => {
      const { designInputs, validate, validationErrors } = useProjectForm(mockApi())
      designInputs.dailyInboundMassTons = 0
      designInputs.rawStorageRatio = 1.5

      expect(validate()).toBe(false)
      expect(validationErrors.value.length).toBeGreaterThan(0)
      expect(validationErrors.value.some(e => e.field === 'dailyInboundMassTons')).toBe(true)
      expect(validationErrors.value.some(e => e.field === 'rawStorageRatio')).toBe(true)
    })
  })

  describe('submit()', () => {
    it('calls the planning API and returns the response on success', async () => {
      const api = mockApi()
      const fakeResponse: PlanningRunResponse = {
        success: true,
        summary: {
          total_area_m2: 1813.57,
          total_position_count: 346,
          total_investment_cny: 6_150_400,
          total_power_kw: 1352.63,
          requires_review: true
        },
        zone_plan: { result: { zones: [] } },
        investment_estimate: { result: { items: [] } },
        power_configuration: {
          equipment_rows: [],
          summary_rows: [],
          items: [],
          total_installed_power_kw: 0,
          total_estimated_demand_kw: 0,
          requires_review: false
        }
      }
      api.run.mockResolvedValue(fakeResponse)

      const { submit } = useProjectForm(api)
      const result = await submit()

      expect(result).not.toBeNull()
      expect(result!.response).toBe(fakeResponse)
      expect(api.run).toHaveBeenCalledTimes(1)
    })

    it('does not call the API when validation fails', async () => {
      const api = mockApi()
      const { designInputs, submit } = useProjectForm(api)
      designInputs.dailyInboundMassTons = -1

      const result = await submit()

      expect(result).toBeNull()
      expect(api.run).not.toHaveBeenCalled()
    })

    it('sets submitError on API failure', async () => {
      const api = mockApi()
      api.run.mockRejectedValue(new Error('Network error'))

      const { submit, submitError } = useProjectForm(api)
      const result = await submit()

      expect(result).toBeNull()
      expect(submitError.value).toBe('Network error')
    })

    it('toggles submitting ref during the request', async () => {
      const api = mockApi()
      api.run.mockResolvedValue({
        success: true,
        summary: {
          total_area_m2: 0,
          total_position_count: 0,
          total_investment_cny: 0,
          total_power_kw: 0,
          requires_review: false
        },
        zone_plan: { result: { zones: [] } },
        investment_estimate: { result: { items: [] } },
        power_configuration: {
          equipment_rows: [],
          summary_rows: [],
          items: [],
          total_installed_power_kw: 0,
          total_estimated_demand_kw: 0,
          requires_review: false
        }
      })

      const { submit, submitting } = useProjectForm(api)

      const submitPromise = submit()
      expect(submitting.value).toBe(true)
      await submitPromise
      expect(submitting.value).toBe(false)
    })
  })

  describe('reset()', () => {
    it('restores design inputs and factory overview to defaults', () => {
      const { designInputs, factoryOverview, reset, submitError, validationErrors } =
        useProjectForm(mockApi())

      designInputs.dailyInboundMassTons = 100
      factoryOverview.factoryName = 'Changed'
      submitError.value = 'some error'
      validationErrors.value = [{ field: 'dailyInboundMassTons', message: '必须大于 0' }]

      reset()

      expect({ ...designInputs }).toEqual(createDefaultDesignInputs())
      expect({ ...factoryOverview }).toEqual(createDefaultFactoryOverview())
      expect(submitError.value).toBe('')
      expect(validationErrors.value).toEqual([])
    })
  })
})
