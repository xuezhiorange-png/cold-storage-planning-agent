import { reactive, ref, type Ref } from 'vue'

import {
  createDefaultDesignInputs,
  DEMO_MIGRATION_GAP_COEFFICIENTS,
  mapDesignInputsToPlanningRequest,
  mapPersistedInputsToDesignInputs,
  validateDesignInputs,
  type DesignInputs,
  type DesignInputValidationError
} from '../model/designInputs'
import type { PlanningRunRequest } from '../../../api/contracts/planning'
import { createProjectsApi } from '../../workflow/api/projectsApi'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'

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
  /** Submit the form (validates first, then calls submitHandler if provided). Returns true if validation passed. */
  submit: () => Promise<boolean>
  /** Reset all inputs to defaults */
  reset: () => void
  /** Load persisted project inputs into the form when available */
  loadPersistedInputs: () => Promise<void>
}

/**
 * Composable for managing project form state.
 *
 * - Only handles form state, validation, request mapping, dirty/reset.
 * - Does NOT make API calls. Accepts an optional `submitHandler` callback
 *   that receives the mapped `PlanningRunRequest` on successful validation.
 * - Tracks a request counter so that a superseded (stale) submit's `finally`
 *   block does not clear `submitting` while a newer submit is still in flight.
 */
export function useProjectForm(
  submitHandler?: (request: PlanningRunRequest) => Promise<void>
): UseProjectFormReturn {
  const workbench = useWorkbenchContextStore()
  const designInputs = reactive<DesignInputs>({ ...createDefaultDesignInputs() })
  const factoryOverview = reactive<FactoryOverview>({ ...createDefaultFactoryOverview() })

  const submitting = ref(false)
  const submitError = ref('')
  const validationErrors = ref<DesignInputValidationError[]>([])

  /** Monotonically increasing counter to identify the most recent submit call. */
  let currentRequestId = 0

  async function hydrateFromPersistedInputs(): Promise<void> {
    if (!workbench.projectId || workbench.versionNumber === null) return
    try {
      const version = await createProjectsApi().getVersion(
        workbench.projectId,
        workbench.versionNumber
      )
      const partial = mapPersistedInputsToDesignInputs(version.input_snapshot ?? {})
      for (const key of Object.keys(partial) as Array<keyof DesignInputs>) {
        const value = partial[key]
        if (value !== undefined) {
          designInputs[key] = value
        }
      }
    } catch {
      // Keep form defaults when persisted inputs are unavailable.
    }
  }

  if (workbench.isReady) {
    hydrateFromPersistedInputs()
  }

  async function loadPersistedInputs(): Promise<void> {
    await hydrateFromPersistedInputs()
  }

  function validate(): boolean {
    const errors = validateDesignInputs(designInputs)
    validationErrors.value = errors
    return errors.length === 0
  }

  async function submit(): Promise<boolean> {
    submitError.value = ''
    validationErrors.value = []

    if (!validate()) {
      return false
    }

    const requestId = ++currentRequestId
    submitting.value = true

    try {
      const request = mapDesignInputsToPlanningRequest(designInputs)
      await submitHandler?.(request)
      // Guard: only current request reports success
      if (requestId !== currentRequestId) {
        return false
      }
      return true
    } catch (error: unknown) {
      if (requestId === currentRequestId) {
        const message =
          error instanceof Error ? error.message : '提交失败，请检查后端服务'
        submitError.value = message
      }
      return false
    } finally {
      // Only clear submitting if this submit is still the most recent call.
      // This prevents a stale finally from hiding a newer in-flight request.
      if (requestId === currentRequestId) {
        submitting.value = false
      }
    }
  }

  function reset(): void {
    currentRequestId += 1  // Invalidate all in-flight submits
    submitting.value = false  // Immediately reset submitting

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
    reset,
    loadPersistedInputs
  }
}
