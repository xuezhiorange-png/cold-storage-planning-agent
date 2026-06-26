import { reactive, ref, type Ref } from 'vue'

import {
  createDefaultDesignInputs,
  mapDesignInputsToPlanningRequest,
  validateDesignInputs,
  type DesignInputs,
  type DesignInputValidationError
} from '../model/designInputs'
import { LatestRequestGate } from '../../../shared/composables/latestRequestGate'
import { createPlanningApi, type PlanningApi } from '../../../features/calculations/api/planningApi'
import { isRequestCancelled } from '../../../api/errors'
import type { PlanningRunResponse } from '../../../api/contracts/planning'

export interface FactoryOverview {
  factoryName: string
  plantingAreaMu: number
  mainVarieties: string
}

export function createDefaultFactoryOverview(): FactoryOverview {
  return {
    factoryName: '蓝莓加工厂',
    plantingAreaMu: 1250,
    mainVarieties: '蓝莓'
  }
}

export interface ProjectSubmitResult {
  response: PlanningRunResponse
}

export interface UseProjectFormReturn {
  /** Reactive design inputs, bound directly to form controls */
  designInputs: DesignInputs
  /** Reactive factory overview fields */
  factoryOverview: FactoryOverview
  /** True while a submit is in flight */
  submitting: Ref<boolean>
  /** Last submit error message (cleared on next submit) */
  submitError: Ref<string>
  /** Per-field validation errors from the last validate() call */
  validationErrors: Ref<DesignInputValidationError[]>
  /** Validate all inputs. Returns true if valid. */
  validate: () => boolean
  /** Submit the form (validates first, then calls the planning API) */
  submit: () => Promise<ProjectSubmitResult | null>
  /** Reset all inputs to defaults */
  reset: () => void
}

export function useProjectForm(planningApi: PlanningApi = createPlanningApi()): UseProjectFormReturn {
  const designInputs = reactive<DesignInputs>({ ...createDefaultDesignInputs() })
  const factoryOverview = reactive<FactoryOverview>({ ...createDefaultFactoryOverview() })

  const submitting = ref(false)
  const submitError = ref('')
  const validationErrors = ref<DesignInputValidationError[]>([])

  const gate = new LatestRequestGate()

  function validate(): boolean {
    const errors = validateDesignInputs(designInputs)
    validationErrors.value = errors
    return errors.length === 0
  }

  async function submit(): Promise<ProjectSubmitResult | null> {
    submitError.value = ''
    validationErrors.value = []

    if (!validate()) {
      return null
    }

    submitting.value = true

    try {
      const handle = gate.begin()
      const request = mapDesignInputsToPlanningRequest(designInputs)

      const response = await planningApi.run(request, handle.signal)

      if (!handle.isCurrent()) {
        return null
      }

      handle.finish()
      return { response }
    } catch (error: unknown) {
      if (isRequestCancelled(error)) {
        return null
      }
      const message =
        error instanceof Error ? error.message : '提交失败，请检查后端服务'
      submitError.value = message
      return null
    } finally {
      submitting.value = false
    }
  }

  function reset(): void {
    const defaults = createDefaultDesignInputs()
    for (const key of Object.keys(defaults) as Array<keyof DesignInputs>) {
      designInputs[key] = defaults[key]
    }
    const overviewDefaults = createDefaultFactoryOverview()
    Object.assign(factoryOverview, overviewDefaults)
    submitError.value = ''
    validationErrors.value = []
  }

  return {
    designInputs,
    factoryOverview,
    submitting,
    submitError,
    validationErrors,
    validate,
    submit,
    reset
  }
}
