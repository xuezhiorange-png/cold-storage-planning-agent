import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface CalculationsApi {
  list(projectId: string, version: number, signal?: AbortSignal): Promise<CalculationRunRecord[]>
}

export function createCalculationsApi(client: HttpClient = apiClient): CalculationsApi {
  return {
    list(projectId, version, signal) {
      return client.requestJson<CalculationRunRecord[]>(
        `/api/v1/projects/${projectId}/versions/${version}/calculations`,
        { signal }
      )
    }
  }
}

export const calculationsApi = createCalculationsApi()
