import { describe, expect, it, vi } from 'vitest'

import { createDefaultDesignInputs } from '../model/designInputs'
import {
  useProjectForm,
  createDefaultFactoryOverview,
  type FactoryOverview
} from './useProjectForm'

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
      const { designInputs } = useProjectForm()
      expect({ ...designInputs }).toEqual(createDefaultDesignInputs())
    })

    it('starts with default factory overview', () => {
      const { factoryOverview } = useProjectForm()
      expect({ ...factoryOverview }).toEqual(createDefaultFactoryOverview())
    })

    it('starts empty submitting, submitError, and validationErrors', () => {
      const { submitting, submitError, validationErrors } = useProjectForm()
      expect(submitting.value).toBe(false)
      expect(submitError.value).toBe('')
      expect(validationErrors.value).toEqual([])
    })
  })

  describe('validate()', () => {
    it('returns true when all inputs are valid', () => {
      const { validate } = useProjectForm()
      expect(validate()).toBe(true)
    })

    it('returns false and populates validationErrors for invalid inputs', () => {
      const { designInputs, validate, validationErrors } = useProjectForm()
      designInputs.dailyInboundMassTons = 0
      designInputs.rawStorageRatio = 1.5

      expect(validate()).toBe(false)
      expect(validationErrors.value.length).toBeGreaterThan(0)
      expect(validationErrors.value.some(e => e.field === 'dailyInboundMassTons')).toBe(true)
      expect(validationErrors.value.some(e => e.field === 'rawStorageRatio')).toBe(true)
    })
  })

  describe('submit()', () => {
    it('calls the submitHandler with mapped request on success', async () => {
      const handler = vi.fn()
      const { submit } = useProjectForm(handler)
      const result = await submit()

      expect(result).toBe(true)
      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          daily_inbound_mass_kg: expect.any(Number),
          working_time_h_per_day: expect.any(Number)
        })
      )
    })

    it('does not call submitHandler when validation fails', async () => {
      const handler = vi.fn()
      const { designInputs, submit } = useProjectForm(handler)
      designInputs.dailyInboundMassTons = -1

      const result = await submit()

      expect(result).toBe(false)
      expect(handler).not.toHaveBeenCalled()
    })

    it('sets submitError when submitHandler throws', async () => {
      const handler = vi.fn().mockRejectedValue(new Error('Network error'))

      const { submit, submitError } = useProjectForm(handler)
      const result = await submit()

      expect(result).toBe(false)
      expect(submitError.value).toBe('Network error')
    })

    it('toggles submitting ref during the request', async () => {
      const handler = vi.fn()
      const { submit, submitting } = useProjectForm(handler)

      const submitPromise = submit()
      expect(submitting.value).toBe(true)
      await submitPromise
      expect(submitting.value).toBe(false)
    })

    it('supports undefined submitHandler (for testing without API)', async () => {
      const { submit } = useProjectForm()
      const result = await submit()

      expect(result).toBe(true)
    })

    it('lets only the most recent request control the submitting flag', async () => {
      let resolveFirst!: () => void
      const firstPromise = new Promise<void>(resolve => { resolveFirst = resolve })
      let resolveSecond!: () => void
      const secondPromise = new Promise<void>(resolve => { resolveSecond = resolve })

      const handler = vi.fn()
        .mockReturnValueOnce(firstPromise)
        .mockReturnValueOnce(secondPromise)

      const { submit, submitting } = useProjectForm(handler)

      // Start first submit
      const firstSubmit = submit()
      expect(submitting.value).toBe(true)

      // Start second submit while first is still pending
      const secondSubmit = submit()
      expect(submitting.value).toBe(true)

      // Resolve first handler — its finally should NOT clear submitting
      resolveFirst!()
      await firstSubmit
      expect(submitting.value).toBe(true) // Still true because second is in flight

      // Resolve second handler — now submitting should clear
      resolveSecond!()
      await secondSubmit
      expect(submitting.value).toBe(false)
    })
  })

  describe('reset()', () => {
    it('restores design inputs and factory overview to defaults', () => {
      const { designInputs, factoryOverview, reset, submitError, validationErrors } =
        useProjectForm()

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
