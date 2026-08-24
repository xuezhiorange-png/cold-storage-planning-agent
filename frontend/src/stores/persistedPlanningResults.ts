import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { PlanningRunResponse } from '../api/contracts/planning'
import { createCalculationsApi, type CalculationsApi } from '../features/calculations/api/calculationsApi'
import { mapPersistedCalculationsToPlanningResponse } from '../features/calculations/model/mapPersistedCalculations'
import { useWorkbenchContextStore } from './workbenchContext'

export const usePersistedPlanningResultsStore = defineStore('persistedPlanningResults', () => {
  const persistedResponse = ref<PlanningRunResponse | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  let loadAbort: AbortController | null = null
  let loadRequestId = 0

  const displayResponse = computed<PlanningRunResponse | null>(() => persistedResponse.value)

  async function load(
    calculationsApi: CalculationsApi = createCalculationsApi()
  ): Promise<PlanningRunResponse | null> {
    const workbench = useWorkbenchContextStore()
    if (!workbench.projectId || workbench.versionNumber === null) {
      persistedResponse.value = null
      return null
    }

    loadAbort?.abort()
    const controller = new AbortController()
    loadAbort = controller
    const requestId = ++loadRequestId
    isLoading.value = true
    error.value = ''

    try {
      const records = await calculationsApi.list(
        workbench.projectId,
        workbench.versionNumber,
        controller.signal
      )
      if (requestId !== loadRequestId || controller.signal.aborted) {
        return null
      }
      const mapped = mapPersistedCalculationsToPlanningResponse(records)
      persistedResponse.value = mapped
      return mapped
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return null
      }
      if (requestId === loadRequestId) {
        error.value = err instanceof Error ? err.message : '持久化计算结果加载失败'
        persistedResponse.value = null
      }
      return null
    } finally {
      if (requestId === loadRequestId && !controller.signal.aborted) {
        isLoading.value = false
      }
    }
  }

  function resetForTests(): void {
    loadAbort?.abort()
    persistedResponse.value = null
    isLoading.value = false
    error.value = ''
  }

  return {
    persistedResponse,
    displayResponse,
    isLoading,
    error,
    load,
    resetForTests
  }
})
