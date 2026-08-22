import type { SchemeComparisonResponse, SchemeItemContract } from '../../../api/contracts/schemes'
import { apiClient, type HttpClient } from '../../../api/httpClient'

export interface SchemeRunListItem {
  run_id: string
  status: string
  recommended_scheme_code: string | null
}

export interface SchemeRunDetailResponse {
  run_id: string
  recommended_scheme_code: string | null
  requires_review: boolean
  candidates: Array<{
    scheme_code: string
    feasible: boolean
    rank: number | null
    total_score: string | null
    result_snapshot: Record<string, unknown>
    constraint_results: Array<Record<string, unknown>>
  }>
}

function parseOptionalNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

export function mapSchemeRunToComparison(
  run: SchemeRunDetailResponse
): SchemeComparisonResponse {
  const schemes: SchemeItemContract[] = run.candidates.map((candidate) => {
    const snapshot = candidate.result_snapshot ?? {}
    return {
      scheme_code: candidate.scheme_code,
      scheme_name: candidate.scheme_code,
      feasible: candidate.feasible,
      total_score: candidate.total_score ?? '0',
      total_area_m2: parseOptionalNumber(snapshot.total_area_m2),
      total_position_count: parseOptionalNumber(snapshot.total_position_count),
      room_module_count: parseOptionalNumber(snapshot.room_module_count),
      door_count: parseOptionalNumber(snapshot.door_count),
      investment_cny: parseOptionalNumber(snapshot.investment_cny),
      installed_power_kw_e: parseOptionalNumber(snapshot.installed_power_kw_e),
      requires_review: Boolean(snapshot.requires_review ?? run.requires_review)
    }
  })

  return {
    schemes,
    recommended_scheme_code: run.recommended_scheme_code,
    weight_set_name: '项目持久化方案比选',
    weight_set_status: run.requires_review ? 'pending_review' : 'persisted'
  }
}

export interface SchemesApi {
  getComparison(
    projectId: string,
    version: number,
    signal?: AbortSignal
  ): Promise<SchemeComparisonResponse>
}

export function createSchemesApi(client: HttpClient = apiClient): SchemesApi {
  return {
    async getComparison(projectId, version, signal) {
      const runs = await client.requestJson<SchemeRunListItem[]>(
        `/api/v1/projects/${projectId}/versions/${version}/scheme-runs`,
        { signal }
      )
      if (!runs.length) {
        return {
          schemes: [],
          recommended_scheme_code: null,
          weight_set_name: '项目持久化方案比选',
          weight_set_status: 'empty'
        }
      }
      const latestRun = runs[runs.length - 1]
      const detail = await client.requestJson<SchemeRunDetailResponse>(
        `/api/v1/projects/${projectId}/versions/${version}/scheme-runs/${latestRun.run_id}`,
        { signal }
      )
      return mapSchemeRunToComparison(detail)
    }
  }
}

export const schemesApi = createSchemesApi()
