import { createPinia, setActivePinia } from 'pinia'

import { useWorkbenchContextStore } from '../../src/stores/workbenchContext'

type FetchMock = {
  mockResolvedValueOnce: (value: Response) => FetchMock
  mockImplementation?: (
    fn: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  ) => unknown
}

export function setupSchemesPagePinia(): ReturnType<typeof createPinia> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const workbench = useWorkbenchContextStore()
  workbench.projectId = 'proj-1'
  workbench.versionNumber = 1
  return pinia
}

export function mockSchemeRunFetch(
  fetchMock: FetchMock,
  schemes: Array<Record<string, unknown>>,
  recommended: string | null = null
) {
  const candidates = schemes.map((scheme, index) => ({
    scheme_code: scheme.scheme_code,
    feasible: scheme.feasible,
    rank: index + 1,
    total_score: scheme.total_score,
    result_snapshot: {
      total_area_m2: scheme.total_area_m2,
      total_position_count: scheme.total_position_count,
      room_module_count: scheme.room_module_count,
      door_count: scheme.door_count,
      investment_cny: scheme.investment_cny,
      installed_power_kw_e: scheme.installed_power_kw_e,
      requires_review: scheme.requires_review
    },
    constraint_results: []
  }))

  if (schemes.length === 0) {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([])))
    return
  }

  fetchMock
    .mockResolvedValueOnce(new Response(JSON.stringify([{ run_id: 'run-1', status: 'completed' }])))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          run_id: 'run-1',
          recommended_scheme_code: recommended,
          requires_review: false,
          candidates
        })
      )
    )
}
