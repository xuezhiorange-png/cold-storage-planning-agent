import { apiClient, type HttpClient } from '../../../api/httpClient'

export const PRODUCTION_WEIGHT_SET_REVISION_ID = 'wsr-production-default-v1'
export const PRODUCTION_PROFILE_CODES = ['balanced'] as const

export interface ProductionSchemeRunResponse {
  run_id: string
  project_id: string
  project_version_id: string
  source_mode: string
  source_binding_id: string
  weight_set_revision_id: string
  status: string
  generator_version: string
  recommended_scheme_code: string | null
  requires_review: boolean
  review_reasons: Array<Record<string, unknown>>
  combined_source_hash: string
  content_hash: string
}

export interface ProductionSchemeRunApi {
  createRun(
    projectId: string,
    versionNumber: number,
    signal?: AbortSignal
  ): Promise<ProductionSchemeRunResponse>
}

function segment(value: string): string {
  return encodeURIComponent(value)
}

export function createProductionSchemeRunApi(
  client: HttpClient = apiClient
): ProductionSchemeRunApi {
  return {
    createRun(projectId, versionNumber, signal) {
      return client.requestJson<ProductionSchemeRunResponse>(
        `/api/v1/projects/${segment(projectId)}/versions/${versionNumber}/production-scheme-runs`,
        {
          method: 'POST',
          body: {
            profile_codes: [...PRODUCTION_PROFILE_CODES],
            weight_set_revision_id: PRODUCTION_WEIGHT_SET_REVISION_ID,
            profile_parameters: {}
          },
          signal
        }
      )
    }
  }
}

export const productionSchemeRunApi = createProductionSchemeRunApi()
