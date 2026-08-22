import type {
  PlanningRunRequest,
  PlanningRunResponse
} from '../../../api/contracts/planning'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface PlanningApi {
  runProject(
    projectId: string,
    version: number,
    request: PlanningRunRequest,
    signal?: AbortSignal
  ): Promise<PlanningRunResponse>
}

export function createPlanningApi(client: HttpClient = apiClient): PlanningApi {
  return {
    runProject(projectId, version, request, signal) {
      return client.requestJson<PlanningRunResponse>(
        `/api/v1/projects/${projectId}/versions/${version}/planning-run`,
        {
          method: 'POST',
          body: request,
          signal
        }
      )
    }
  }
}

export const planningApi = createPlanningApi()
