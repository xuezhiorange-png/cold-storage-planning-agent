import { apiClient, type HttpClient } from '../../../api/httpClient'
import type { SchemeComparisonResponse } from '../../../api/contracts/schemes'

export interface SchemesApi {
  getComparison(signal?: AbortSignal): Promise<SchemeComparisonResponse>
}

export function createSchemesApi(client: HttpClient = apiClient): SchemesApi {
  return {
    async getComparison(signal?: AbortSignal): Promise<SchemeComparisonResponse> {
      return client.requestJson<SchemeComparisonResponse>('/api/v1/demo/scheme-comparison', { signal })
    }
  }
}

export const schemesApi = createSchemesApi()
