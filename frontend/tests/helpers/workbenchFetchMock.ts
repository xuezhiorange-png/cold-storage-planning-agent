import type { WorkflowAggregateV1 } from '../../src/api/contracts/workflow'
import type { PlanningRunResponse } from '../../src/api/contracts/planning'

type FetchMock = {
  mockImplementation: (
    fn: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  ) => unknown
  getMockImplementation?: () =>
    | ((input: RequestInfo | URL, init?: RequestInit) => Promise<Response>)
    | undefined
}

export function sampleWorkflowAggregate(
  overrides: Partial<WorkflowAggregateV1> = {}
): WorkflowAggregateV1 {
  return {
    contract_version: 'WorkflowAggregateV1',
    generated_at: '2026-01-01T00:00:00Z',
    project_context: {
      project_id: 'proj-test',
      project_code: 'P001',
      project_name: '测试项目',
      project_version_id: 'ver-1',
      project_version_number: 1,
      project_version_status: 'draft',
      revision_stale: false,
      revision_stale_reasons: [],
      revision_freshness: 'fresh'
    },
    current_step: 'PROJECT_INPUT',
    workflow_status: 'IN_PROGRESS',
    workflow_goal: 'formal_report',
    steps: [],
    blockers: [],
    primary_action_id: '',
    next_required_actions: [],
    workflow_readiness: {
      status: 'NOT_READY',
      blockers: [],
      reasons: [],
      next_required_actions: []
    },
    formal_export_eligibility: {
      eligible: false,
      status: 'INELIGIBLE',
      blockers: [{ code: 'REPORT_MISSING', message: 'No report', stage: 'FORMAL_REPORT' }],
      authority_owner: 'reports_module_p1_lifecycle',
      revalidation_required: true
    },
    agent_assistance: {
      available: false,
      status: 'UNAVAILABLE',
      blocking_core_workflow: false,
      capability_state: 'AGENT_CAPABILITY_DISABLED'
    },
    ...overrides
  }
}

export function samplePlanningRunResponse(): PlanningRunResponse {
  return {
    success: true,
    summary: {
      total_area_m2: 850,
      total_position_count: 300,
      total_investment_cny: 3_000_000,
      total_power_kw: 1350,
      requires_review: false
    },
    zone_plan: { result: { zones: [] } },
    investment_estimate: { result: { items: [] } },
    power_configuration: {
      equipment_rows: [],
      summary_rows: [],
      items: [],
      total_installed_power_kw: 0,
      total_estimated_demand_kw: 0,
      requires_review: false
    }
  }
}

export function installWorkbenchFetchMock(
  fetchMock: FetchMock,
  options: {
    agentAvailable?: boolean
    workflow?: WorkflowAggregateV1
    planningRunError?: Error
    planningRunResponse?: PlanningRunResponse
    deferPlanningRun?: boolean
  } = {}
) {
  let resolvePlanningRun: ((response: Response) => void) | null = null
  let lastPlanningRunSignal: AbortSignal | null = null
  const workflow = options.workflow ?? sampleWorkflowAggregate(
    options.agentAvailable
      ? {
          agent_assistance: {
            available: true,
            status: 'AVAILABLE',
            blocking_core_workflow: false,
            capability_state: 'LOCAL_TEST_AVAILABLE'
          }
        }
      : {}
  )

  fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'

    if (url.includes('/health/ready')) {
      return new Response(
        JSON.stringify({
          status: 'ready',
          capabilities: [
            {
              name: 'model_backed_agent',
              status: options.agentAvailable ? 'available' : 'disabled',
              capability_state: options.agentAvailable
                ? 'LOCAL_TEST_AVAILABLE'
                : 'AGENT_CAPABILITY_DISABLED'
            }
          ]
        })
      )
    }

    if (url.includes('/workflow')) {
      return new Response(JSON.stringify(workflow))
    }

    if (url.includes('/api/v1/projects') && method === 'POST' && !url.includes('/versions/')) {
      return new Response(
        JSON.stringify({ id: 'proj-test', code: 'P001', current_version_number: 1 })
      )
    }

    if (url.match(/\/api\/v1\/projects\/[^/]+$/)) {
      return new Response(
        JSON.stringify({
          id: 'proj-test',
          code: 'P001',
          name: '测试项目',
          location: '山东',
          product_category: 'blueberry',
          status: 'draft',
          current_version_number: 1
        })
      )
    }

    if (url.includes('/versions/1') && !url.includes('planning-run') && method === 'GET') {
      return new Response(
        JSON.stringify({
          id: 'ver-1',
          version_number: 1,
          status: 'draft',
          input_snapshot: {}
        })
      )
    }

    if (url.includes('/planning-run') && method === 'POST') {
      lastPlanningRunSignal = init?.signal ?? null
      if (options.planningRunError) {
        throw options.planningRunError
      }
      const body = JSON.stringify(options.planningRunResponse ?? samplePlanningRunResponse())
      if (options.deferPlanningRun) {
        return new Promise<Response>((resolve, reject) => {
          resolvePlanningRun = resolve
          const signal = init?.signal
          if (signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'))
            return
          }
          if (signal) {
            signal.addEventListener(
              'abort',
              () => reject(new DOMException('Aborted', 'AbortError')),
              { once: true }
            )
          }
        })
      }
      return new Response(body)
    }

    if (url.includes('/scheme-runs') && !url.includes('/comparison') && method === 'GET') {
      return new Response(JSON.stringify([]))
    }

    return new Response('{}', { status: 404 })
  })

  return {
    fetchMock,
    lastPlanningRunSignal: () => lastPlanningRunSignal,
    resolvePlanningRun: (response?: PlanningRunResponse) => {
      resolvePlanningRun?.(
        new Response(JSON.stringify(response ?? samplePlanningRunResponse()))
      )
    }
  }
}
