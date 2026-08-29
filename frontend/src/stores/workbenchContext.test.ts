import { describe, expect, it, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

import type { WorkflowAggregateV1 } from '../api/contracts/workflow'
import { useWorkbenchContextStore } from './workbenchContext'

function sampleWorkflow(agentAvailable = false): WorkflowAggregateV1 {
  return {
    contract_version: 'WorkflowAggregateV2',
    generated_at: '2026-01-01T00:00:00Z',
    project_context: {
      project_id: 'proj-1',
      project_code: 'P001',
      project_name: '测试项目',
      project_version_id: 'ver-1',
      project_version_number: 1,
      project_version_status: 'draft',
      revision_stale: false,
      revision_stale_reasons: [],
      revision_freshness: 'fresh'
    },
    current_step: 'DETERMINISTIC_CALCULATION',
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
      available: agentAvailable,
      status: agentAvailable ? 'AVAILABLE' : 'UNAVAILABLE',
      blocking_core_workflow: false,
      capability_state: agentAvailable ? 'LOCAL_TEST_AVAILABLE' : 'AGENT_CAPABILITY_DISABLED'
    }
  }
}

describe('workbenchContext store consumer semantics', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps formal export eligibility separate from workflow readiness', () => {
    const store = useWorkbenchContextStore()
    store.workflow = sampleWorkflow(false)

    expect(store.workflowReadiness?.status).toBe('NOT_READY')
    expect(store.formalExportEligibility?.eligible).toBe(false)
    expect(store.workflowReadiness?.blockers).toEqual([])
    expect(store.formalExportEligibility?.blockers[0]?.code).toBe('REPORT_MISSING')
  })

  it('does not treat unavailable agent as core workflow blocker', () => {
    const store = useWorkbenchContextStore()
    store.workflow = sampleWorkflow(false)

    expect(store.agentAssistance?.available).toBe(false)
    expect(store.agentAssistance?.blocking_core_workflow).toBe(false)
    expect(store.workflowReadiness?.blockers).toEqual([])
  })

  it('reflects available agent from backend projection', () => {
    const store = useWorkbenchContextStore()
    store.workflow = sampleWorkflow(true)

    expect(store.agentAssistance?.available).toBe(true)
    expect(store.agentAssistance?.status).toBe('AVAILABLE')
  })
})
