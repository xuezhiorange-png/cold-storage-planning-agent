import type {
  PlanningRunRequest,
  PlanningRunResponse
} from '../../../api/contracts/planning'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface PlanningApi {
  run(request: PlanningRunRequest, signal?: AbortSignal): Promise<PlanningRunResponse>
}

export function createPlanningApi(client: HttpClient = apiClient): PlanningApi {
  return {
    run(request: PlanningRunRequest, signal?: AbortSignal): Promise<PlanningRunResponse> {
      return client.requestJson<PlanningRunResponse>('/api/v1/demo/planning-run', {
        method: 'POST',
        body: request,
        signal
      })
    }
  }
}

export const planningApi = createPlanningApi()
