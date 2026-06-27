import { ref, type Ref } from 'vue'

import type { PlanningRunRequest, PlanningRunResponse } from '../../../api/contracts/planning'
import { LatestRequestGate } from '../../../shared/composables/latestRequestGate'
import { createPlanningApi, type PlanningApi } from '../api/planningApi'

export interface UsePlanningRunReturn {
  /** The most recent successful response, or null before the first run. */
  data: Ref<PlanningRunResponse | null>
  /** True while a request is in flight. */
  loading: Ref<boolean>
  /** Human-readable error message, or empty string when no error. */
  error: Ref<string>
  /** Execute a planning run. Aborts any previous in-flight request. */
  execute: (request: PlanningRunRequest) => Promise<PlanningRunResponse | null>
  /** Abort the current request (if any) and reset error state. */
  abort: () => void
  /** Reset data, loading, and error to their initial values. */
  reset: () => void
}

/**
 * Composable that manages a planning run lifecycle.
 *
 * - Cancels the previous request when a new one starts (via LatestRequestGate).
 * - Exposes reactive `data`, `loading`, and `error` state.
 * - Accepts an optional `PlanningApi` for testability.
 */
export function usePlanningRun(api: PlanningApi = createPlanningApi()): UsePlanningRunReturn {
  const gate = new LatestRequestGate()
  const data: Ref<PlanningRunResponse | null> = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function execute(request: PlanningRunRequest): Promise<PlanningRunResponse | null> {
    error.value = ''
    loading.value = true

    const handle = gate.begin()

    try {
      const response = await api.run(request, handle.signal)

      if (handle.isCurrent()) {
        data.value = response
        handle.finish()
        return response
      }
      return null
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return null
      }
      if (handle.isCurrent()) {
        error.value = err instanceof Error ? err.message : '规划运行失败'
      }
      return null
    } finally {
      if (handle.isCurrent()) {
        loading.value = false
      }
    }
  }

  function abort(): void {
    gate.cancel()
    loading.value = false
  }

  function reset(): void {
    gate.cancel()
    data.value = null
    loading.value = false
    error.value = ''
  }

  return { data, loading, error, execute, abort, reset }
}
