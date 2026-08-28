/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import type { WorkflowAggregateV1 } from '../../../api/contracts/workflow'
import { usePersistedPlanningResultsStore } from '../../../stores/persistedPlanningResults'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import {
  sampleFiveStageCalculationRuns,
  sampleWorkflowAggregate
} from '../../../../tests/helpers/workbenchFetchMock'
import WorkflowGuidancePanel from './WorkflowGuidancePanel.vue'

function workflowWithSchemeMissingOnly(): WorkflowAggregateV1 {
  return sampleWorkflowAggregate({
    current_step: 'SCHEME_COMPARISON',
    workflow_status: 'BLOCKED',
    workflow_readiness: {
      status: 'BLOCKED',
      blockers: [
        {
          code: 'CALCULATION_REQUIRES_REVIEW',
          message: 'Calculations require review: investment_estimate'
        },
        {
          code: 'SCHEME_MISSING',
          message: 'No completed scheme run for this version',
          stage: 'SCHEME_COMPARISON'
        }
      ],
      reasons: [],
      next_required_actions: []
    },
    blockers: [
      {
        code: 'CALCULATION_REQUIRES_REVIEW',
        message: 'Calculations require review: investment_estimate',
        stage: 'DETERMINISTIC_CALCULATION'
      },
      {
        code: 'SCHEME_MISSING',
        message: 'No completed scheme run for this version',
        stage: 'SCHEME_COMPARISON'
      }
    ],
    next_required_actions: [
      {
        action_id: 'action-deterministic_calculation',
        type: 'DETERMINISTIC_CALCULATION',
        target_step: 'DETERMINISTIC_CALCULATION',
        label: 'Complete deterministic calculation',
        reason: 'Calculations require review: investment_estimate',
        required: true,
        enabled: false,
        blocked_by: ['CALCULATION_REQUIRES_REVIEW', 'SCHEME_MISSING']
      }
    ]
  })
}

function mountPanel(
  pinia: ReturnType<typeof createPinia>,
  workflow: WorkflowAggregateV1,
  chainComplete: boolean
) {
  const workbench = useWorkbenchContextStore(pinia)
  workbench.projectId = 'proj-test'
  workbench.versionNumber = 1
  workbench.projectName = '测试项目'
  workbench.projectCode = 'P001'
  workbench.workflow = workflow

  const persisted = usePersistedPlanningResultsStore(pinia)
  if (chainComplete) {
    persisted.rawRecords = sampleFiveStageCalculationRuns() as CalculationRunRecord[]
  } else {
    persisted.rawRecords = []
  }

  return mount(WorkflowGuidancePanel, {
    global: {
      plugins: [pinia]
    }
  })
}

describe('WorkflowGuidancePanel', () => {
  const pinia = createPinia()

  beforeEach(() => {
    setActivePinia(pinia)
    useWorkbenchContextStore(pinia).resetForTests()
    usePersistedPlanningResultsStore(pinia).resetForTests()
  })

  it('shows 进行中 with Chinese guidance when only SCHEME_MISSING remains after five-stage persistence', () => {
    const wrapper = mountPanel(pinia, workflowWithSchemeMissingOnly(), true)

    expect(wrapper.text()).toContain('工作流：进行中')
    expect(wrapper.text()).not.toContain('工作流：已阻断')
    expect(wrapper.text()).toContain('还没跑生产方案评分，请到计算结果页运行')
    expect(wrapper.text()).toContain('前往计算结果页运行生产方案评分')
    expect(wrapper.text()).not.toContain('Complete deterministic calculation')
    expect(wrapper.text()).not.toContain('（需先解决阻断项）')
    expect(wrapper.text()).not.toContain('SCHEME_MISSING')
    expect(wrapper.text()).toContain('正式导出与草稿导出不是同一件事')
  })

  it('keeps blocked badge when five stages are not persisted', () => {
    const wrapper = mountPanel(pinia, workflowWithSchemeMissingOnly(), false)

    expect(wrapper.text()).toContain('工作流：已阻断')
    expect(wrapper.text()).toContain('SCHEME_MISSING')
    expect(wrapper.text()).toContain('Complete deterministic calculation')
    expect(wrapper.text()).toContain('（需先解决阻断项）')
  })
})
