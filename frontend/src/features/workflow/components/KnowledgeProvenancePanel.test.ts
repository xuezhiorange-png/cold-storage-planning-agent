import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type { KnowledgeProvenanceProjection } from '../../../api/contracts/workflow'
import { useWorkbenchContextStore } from '../../../stores/workbenchContext'
import KnowledgeProvenancePanel from './KnowledgeProvenancePanel.vue'

function mountPanel(provenance: KnowledgeProvenanceProjection | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const workbench = useWorkbenchContextStore(pinia)
  workbench.workflow = {
    contract_version: 'WorkflowAggregateV1',
    generated_at: '2026-01-01T00:00:00Z',
    project_context: {
      project_id: 'proj-1',
      project_code: 'P001',
      project_name: '测试',
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
      blockers: [],
      authority_owner: 'reports_module_p1_lifecycle',
      revalidation_required: true
    },
    agent_assistance: {
      available: false,
      status: 'UNAVAILABLE',
      blocking_core_workflow: false,
      capability_state: 'AGENT_CAPABILITY_DISABLED'
    },
    knowledge_provenance: provenance ?? undefined
  }

  return mount(KnowledgeProvenancePanel, {
    global: {
      plugins: [pinia]
    }
  })
}

describe('KnowledgeProvenancePanel', () => {
  it('shows not-required message when provenance is not applicable', () => {
    const wrapper = mountPanel({
      required: false,
      available: false,
      status: 'NOT_REQUIRED',
      blockers: [],
      source_references: []
    })

    expect(wrapper.text()).toContain('知识溯源')
    expect(wrapper.text()).toContain('无需溯源')
    expect(wrapper.text()).toContain('未引用知识库修订')
  })

  it('renders page evidence rows for available provenance', () => {
    const wrapper = mountPanel({
      required: true,
      available: true,
      status: 'AVAILABLE',
      blockers: [],
      source_references: [
        {
          revision_id: 'krev-1',
          document_id: 'doc-1',
          document_code: 'KB-001',
          document_title: '冷库设计手册',
          content_sha256: 'abc123',
          original_filename: 'manual.pdf',
          version_label: 'v1',
          revision_number: 1,
          review_status: 'approved',
          requires_review: false,
          requires_ocr: true,
          ingestion_status: 'indexed',
          page_evidence_available: true,
          page_evidence: [
            {
              source_page_evidence_id: 'spe-rev1-p3',
              page_number: 3,
              extraction_method: 'ocr',
              extraction_status: 'completed',
              is_complete: true,
              is_ocr_derived: true,
              requires_review: true,
              review_status: 'unverified',
              confidence: 0.82,
              confidence_source: 'ocr_engine'
            }
          ]
        }
      ]
    })

    expect(wrapper.text()).toContain('KB-001')
    expect(wrapper.text()).toContain('冷库设计手册')
    expect(wrapper.text()).toContain('manual.pdf')
    expect(wrapper.text()).toContain('spe-rev1-p3')
    expect(wrapper.text()).toContain('OCR')
    expect(wrapper.text()).toContain('0.82')
  })

  it('fails closed when page evidence is missing', () => {
    const wrapper = mountPanel({
      required: true,
      available: false,
      status: 'INVALID',
      blockers: [
        {
          code: 'KNOWLEDGE_PROVENANCE_UNAVAILABLE',
          message: 'OCR detection is not OCR evidence; page evidence is missing'
        }
      ],
      source_references: [
        {
          revision_id: 'krev-1',
          document_id: 'doc-1',
          content_sha256: 'abc123',
          requires_review: false,
          requires_ocr: true,
          ingestion_status: 'requires_ocr',
          page_evidence_available: false,
          page_evidence: []
        }
      ]
    })

    expect(wrapper.text()).toContain('溯源无效')
    expect(wrapper.text()).toContain('KNOWLEDGE_PROVENANCE_UNAVAILABLE')
    expect(wrapper.text()).toContain('页面证据缺失')
    expect(wrapper.text()).toContain('未伪造')
  })
})
