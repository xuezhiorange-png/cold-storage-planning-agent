import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { CalculationRunRecord } from '../api/contracts/calculations'
import type { PlanningRunResponse } from '../api/contracts/planning'
import { createCalculationsApi, type CalculationsApi } from '../features/calculations/api/calculationsApi'
import { mapPersistedCalculationsToPlanningResponse } from '../features/calculations/model/mapPersistedCalculations'
import {
  mapFiveStageProgress,
  type FiveStageProgressView
} from '../features/five-stage/model/mapFiveStageCalculations'
import { useWorkbenchContextStore } from './workbenchContext'

export const usePersistedPlanningResultsStore = defineStore('persistedPlanningResults', () => {
  const rawRecords = ref<CalculationRunRecord[]>([])
  const persistedResponse = ref<PlanningRunResponse | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  let loadAbort: AbortController | null = null
  let loadRequestId = 0

  const displayResponse = computed<PlanningRunResponse | null>(() => persistedResponse.value)

  const fiveStageProgress = computed<FiveStageProgressView>(() => {
    const workbench = useWorkbenchContextStore()
    const versionStatus = workbench.workflow?.project_context.project_version_status
    return mapFiveStageProgress(rawRecords.value, {
      versionLocked:
        versionStatus === 'approved' ||
        versionStatus === 'archived'
    })
  })

  async function load(
    calculationsApi: CalculationsApi = createCalculationsApi()
  ): Promise<PlanningRunResponse | null> {
    const workbench = useWorkbenchContextStore()
    if (!workbench.projectId || workbench.versionNumber === null) {
      rawRecords.value = []
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
      rawRecords.value = records
      const mapped = mapPersistedCalculationsToPlanningResponse(records)
      persistedResponse.value = mapped
      return mapped
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return null
      }
      if (requestId === loadRequestId) {
        error.value = err instanceof Error ? err.message : '持久化计算结果加载失败'
        rawRecords.value = []
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
    rawRecords.value = []
    persistedResponse.value = null
    isLoading.value = false
    error.value = ''
  }

  return {
    rawRecords,
    persistedResponse,
    displayResponse,
    fiveStageProgress,
    isLoading,
    error,
    load,
    resetForTests
  }
})
