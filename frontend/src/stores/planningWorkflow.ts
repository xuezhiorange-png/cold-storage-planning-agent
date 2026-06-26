import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PlanningRunRequest, PlanningRunResponse } from '../api/contracts/planning'
import { createPlanningApi, type PlanningApi } from '../features/calculations/api/planningApi'

export const usePlanningWorkflowStore = defineStore('planningWorkflow', () => {
  const latestRequest = ref<PlanningRunRequest | null>(null)
  const latestResponse = ref<PlanningRunResponse | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  let abortController: AbortController | null = null
  let requestId = 0

  async function execute(request: PlanningRunRequest, api: PlanningApi = createPlanningApi()): Promise<PlanningRunResponse | null> {
    // Cancel previous
    abortController?.abort()

    const id = ++requestId
    const controller = new AbortController()
    abortController = controller

    latestRequest.value = request
    error.value = ''
    isLoading.value = true

    try {
      const response = await api.run(request, controller.signal)

      // Only current request writes state
      if (id !== requestId) return null
      if (controller.signal.aborted) return null

      latestResponse.value = response
      isLoading.value = false
      return response
    } catch (err: unknown) {
      if (id !== requestId) return null
      if (err instanceof DOMException && err.name === 'AbortError') {
        isLoading.value = false
        return null
      }
      if (controller.signal.aborted) {
        isLoading.value = false
        return null
      }
      error.value = err instanceof Error ? err.message : '规划运行失败'
      isLoading.value = false
      return null
    }
  }

  function cancel() {
    abortController?.abort()
    abortController = null
    isLoading.value = false
  }

  function reset() {
    cancel()
    latestRequest.value = null
    latestResponse.value = null
    error.value = ''
  }

  return {
    latestRequest,
    latestResponse,
    isLoading,
    error,
    execute,
    cancel,
    reset
  }
})
