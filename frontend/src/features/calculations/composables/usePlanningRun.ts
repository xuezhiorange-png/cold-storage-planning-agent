import { ref, type Ref } from 'vue'

import type { PlanningRunRequest, PlanningRunResponse } from '../../../api/contracts/planning'
import { LatestRequestGate } from '../../../shared/composables/latestRequestGate'
import { createPlanningApi, type PlanningApi } from '../api/planningApi'

export interface UsePlanningRunReturn {
  data: Ref<PlanningRunResponse | null>
  loading: Ref<boolean>
  error: Ref<string>
  execute: (
    projectId: string,
    version: number,
    request: PlanningRunRequest
  ) => Promise<PlanningRunResponse | null>
  abort: () => void
  reset: () => void
}

export function usePlanningRun(api: PlanningApi = createPlanningApi()): UsePlanningRunReturn {
  const gate = new LatestRequestGate()
  const data: Ref<PlanningRunResponse | null> = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function execute(
    projectId: string,
    version: number,
    request: PlanningRunRequest
  ): Promise<PlanningRunResponse | null> {
    error.value = ''
    loading.value = true

    const handle = gate.begin()

    try {
      const response = await api.runProject(projectId, version, request, handle.signal)

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
