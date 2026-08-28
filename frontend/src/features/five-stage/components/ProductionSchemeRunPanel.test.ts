/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import { sampleFiveStageCalculationRuns } from '../../../../tests/helpers/workbenchFetchMock'
import ProductionSchemeRunPanel from './ProductionSchemeRunPanel.vue'

const createRun = vi.fn()

vi.mock('./productionSchemeRunApi', () => ({
  createProductionSchemeRunApi: () => ({
    createRun
  })
}))

function seedFiveStageRecords(pinia: ReturnType<typeof createPinia>): void {
  const persisted = usePersistedPlanningResultsStore(pinia)
  persisted.rawRecords = sampleFiveStageCalculationRuns() as unknown as CalculationRunRecord[]
}

function seedPartialFiveStageRecords(pinia: ReturnType<typeof createPinia>): void {
  const persisted = usePersistedPlanningResultsStore(pinia)
  persisted.rawRecords = sampleFiveStageCalculationRuns().slice(0, 2) as unknown as CalculationRunRecord[]
}

function mountPanel(pinia: ReturnType<typeof createPinia>) {
  return mount(ProductionSchemeRunPanel, {
    global: {
      plugins: [pinia]
    }
  })
}

function setupWorkbench(
  pinia: ReturnType<typeof createPinia>,
  calcStatus: 'COMPLETED' | 'REVIEW_REQUIRED'
): void {
  const workbench = useWorkbenchContextStore(pinia)
  workbench.projectId = 'proj-test'
  workbench.versionNumber = 1
  workbench.workflow = {
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
    current_step: 'SCHEME_COMPARISON',
    workflow_status: 'BLOCKED',
    workflow_goal: 'formal_report',
    steps: [
      {
        step: 'DETERMINISTIC_CALCULATION',
        applicability: 'REQUIRED',
        status: calcStatus,
        blocking: calcStatus !== 'COMPLETED',
        blockers: []
      }
    ],
    blockers: [],
    primary_action_id: '',
    next_required_actions: [],
    workflow_readiness: {
      status: calcStatus === 'COMPLETED' ? 'NOT_READY' : 'BLOCKED',
      blockers: [],
      reasons: [],
      next_required_actions: []
    },
    formal_export_eligibility: {
      eligible: false,
      status: 'INELIGIBLE',
      blockers: [],
      authority_owner: 'reports_module_p1_lifecycle',
      revalidation_required: true
    },
    agent_assistance: {
      available: false,
      status: 'UNAVAILABLE',
      blocking_core_workflow: false,
      capability_state: 'AGENT_CAPABILITY_DISABLED'
    }
  }
}

describe('ProductionSchemeRunPanel', () => {
  const pinia = createPinia()

  beforeEach(() => {
    setActivePinia(pinia)
    vi.clearAllMocks()
    useWorkbenchContextStore(pinia).resetForTests()
    usePersistedPlanningResultsStore(pinia).resetForTests()
    createRun.mockResolvedValue({
      run_id: 'run-1',
      project_id: 'proj-test',
      project_version_id: 'ver-1',
      source_mode: 'production',
      source_binding_id: 'binding-1',
      weight_set_revision_id: 'wsr-production-default-v1',
      status: 'completed',
      generator_version: '1.0.0',
      recommended_scheme_code: 'balanced',
      requires_review: true,
      review_reasons: [],
      combined_source_hash: 'hash-combined',
      content_hash: 'hash-content'
    })
  })

  it('enables the run button when persisted chainComplete is true even if calc step is REVIEW_REQUIRED', async () => {
    setupWorkbench(pinia, 'REVIEW_REQUIRED')
    vi.spyOn(usePersistedPlanningResultsStore(pinia), 'load').mockResolvedValue(null)
    seedFiveStageRecords(pinia)

    const wrapper = mountPanel(pinia)
    await flushPromises()

    const button = wrapper.get('button')
    expect(button.element.hasAttribute('disabled')).toBe(false)
    expect(wrapper.text()).toContain('生产方案评分')
    expect(wrapper.text()).not.toContain('production-scheme-runs')
    expect(wrapper.text()).not.toContain('需先完成五阶段持久化')
  })

  it('keeps the button disabled when persisted chainComplete is false even if calc step is COMPLETED', async () => {
    setupWorkbench(pinia, 'COMPLETED')
    vi.spyOn(usePersistedPlanningResultsStore(pinia), 'load').mockResolvedValue(null)
    seedPartialFiveStageRecords(pinia)

    const wrapper = mountPanel(pinia)
    await flushPromises()

    const button = wrapper.get('button')
    expect(button.element.hasAttribute('disabled')).toBe(true)
    expect(wrapper.text()).toContain('需先完成五阶段持久化')
  })

  it('posts to production-scheme-runs when chainComplete enables the button', async () => {
    setupWorkbench(pinia, 'REVIEW_REQUIRED')
    vi.spyOn(usePersistedPlanningResultsStore(pinia), 'load').mockResolvedValue(null)
    seedFiveStageRecords(pinia)

    const wrapper = mountPanel(pinia)
    await flushPromises()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(createRun).toHaveBeenCalledWith('proj-test', 1)
    expect(wrapper.text()).toContain('运行 ID')
    expect(wrapper.text()).toContain('结果哈希')
    expect(wrapper.text()).toContain('hash-combined')
  })
})
