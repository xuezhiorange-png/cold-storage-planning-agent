import type { CapabilityProjectionEntry } from '../../../api/contracts/capabilities'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface RuntimeReadyResponse {
  status?: string
  state?: string
  capabilities?: CapabilityProjectionEntry[]
}

export interface RuntimeApi {
  getReady(signal?: AbortSignal): Promise<RuntimeReadyResponse>
}

export function createRuntimeApi(client: HttpClient = apiClient): RuntimeApi {
  return {
    async getReady(signal) {
      return client.requestJson<RuntimeReadyResponse>('/health/ready', { signal })
    }
  }
}
