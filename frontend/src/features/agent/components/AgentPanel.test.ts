import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import AgentPanel from './AgentPanel.vue'

function mountAgentPanel() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const workbench = useWorkbenchContextStore(pinia)
  workbench.workflow = {
    contract_version: 'WorkflowAggregateV2',
    generated_at: '2026-01-01T00:00:00Z',
    project_context: {
      project_id: 'proj-1',
      project_code: 'P001',
      project_name: 'V0.4 本地示例项目',
      project_version_id: 'ver-1',
      project_version_number: 1,
      project_version_status: 'draft',
      revision_stale: false,
      revision_stale_reasons: [],
      revision_freshness: 'fresh'
    },
    current_step: 'DETERMINISTIC_CALCULATION',
    workflow_status: 'IN_PROGRESS',
    workflow_goal: 'planning_preview',
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
      blockers: [],
      authority_owner: 'reports_module_p1_lifecycle',
      revalidation_required: true
    },
    agent_assistance: {
      available: false,
      status: 'UNAVAILABLE',
      blocking_core_workflow: false,
      capability_state: 'AGENT_CAPABILITY_DISABLED',
      unavailability_reason: 'AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE'
    }
  }

  return mount(AgentPanel, {
    global: {
      plugins: [pinia]
    },
    attachTo: document.body
  })
}

describe('AgentPanel fail-closed projection', () => {
  it('shows unavailable copy and capability state without a message composer', async () => {
    const wrapper = mountAgentPanel()

    const toggleBtn = wrapper.find('button.agent-panel__toggle')
    expect(toggleBtn.classes()).toContain('agent-panel__toggle--unavailable')
    expect(toggleBtn.attributes('aria-label')).toBe('查看 AI 助手不可用说明')

    await toggleBtn.trigger('click')
    await flushPromises()

    const drawer = document.body.querySelector('.agent-panel__drawer')
    expect(drawer).not.toBeNull()
    expect(drawer!.textContent).toContain('AI 助手当前不可用')
    expect(drawer!.textContent).toContain('能力状态：AGENT_CAPABILITY_DISABLED')
    expect(drawer!.textContent).toContain('当前无法发送消息或执行工具操作')
    expect(drawer!.querySelector('textarea')).toBeNull()
    expect(drawer!.querySelector('input[type="text"]')).toBeNull()

    wrapper.unmount()
    document.body.querySelectorAll('.agent-panel__drawer, .agent-panel__overlay').forEach((el) => {
      el.remove()
    })
  })
})
