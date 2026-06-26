import { defineStore } from 'pinia'
import { ref, type Ref } from 'vue'
import type { PlanningRunRequest, PlanningRunResponse } from '../api/contracts/planning'

/**
 * Planning workflow store for shared session state across routes.
 *
 * Holds the latest request/response with loading and error state so that
 * different route-level components (inputs form, calculation summary,
 * export panel, etc.) can observe and react to the same planning run.
 */
export const usePlanningWorkflowStore = defineStore('planningWorkflow', () => {
  const latestRequest = ref<PlanningRunRequest | null>(null)
  const latestResponse = ref<PlanningRunResponse | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  function setRequest(req: PlanningRunRequest) {
    latestRequest.value = req
  }

  function setResponse(resp: PlanningRunResponse) {
    latestResponse.value = resp
    error.value = ''
    isLoading.value = false
  }

  function setLoading(v: boolean) {
    isLoading.value = v
  }

  function setError(msg: string) {
    error.value = msg
    isLoading.value = false
  }

  function clear() {
    latestRequest.value = null
    latestResponse.value = null
    isLoading.value = false
    error.value = ''
  }

  return {
    latestRequest,
    latestResponse,
    isLoading,
    error,
    setRequest,
    setResponse,
    setLoading,
    setError,
    clear
  }
})
