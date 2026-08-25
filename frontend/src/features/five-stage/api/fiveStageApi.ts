import type {
  FiveStageExecutionRequest,
  FiveStageExecutionResponse
} from '../../../api/contracts/fiveStage'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface FiveStageApi {
  execute(
    projectId: string,
    version: number,
    request: FiveStageExecutionRequest,
    signal?: AbortSignal
  ): Promise<FiveStageExecutionResponse>
}

export function createFiveStageApi(client: HttpClient = apiClient): FiveStageApi {
  return {
    execute(projectId, version, request, signal) {
      return client.requestJson<FiveStageExecutionResponse>(
        `/api/v1/projects/${projectId}/versions/${version}/five-stage-execution`,
        {
          method: 'POST',
          body: request,
          idempotencyKey: request.idempotency_key,
          signal
        }
      )
    }
  }
}

export const fiveStageApi = createFiveStageApi()
