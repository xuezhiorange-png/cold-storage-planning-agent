export interface WorkflowBlocker {
  code: string
  message: string
  stage?: string
  source_type?: string
  source_id?: string
  severity?: string
}

export interface KnowledgePageEvidenceProjection {
  source_page_evidence_id: string
  page_number: number
  extraction_method?: string
  extraction_status: string
  source_authority?: string
  source_content_sha256?: string
  original_filename?: string
  is_complete: boolean
  is_ocr_derived: boolean
  requires_review?: boolean
  review_status?: string
  confidence?: number | null
  confidence_source?: string
  ocr_engine?: string
  ingestion_provenance?: Record<string, unknown>
  document_code?: string
  document_title?: string
}

export interface KnowledgeSourceReferenceProjection {
  revision_id: string
  document_id: string
  document_code?: string
  document_title?: string
  content_sha256: string
  original_filename?: string
  version_label?: string
  revision_number?: number
  review_status?: string
  requires_review: boolean
  requires_ocr: boolean
  ingestion_status: string
  page_evidence: KnowledgePageEvidenceProjection[]
  page_evidence_available: boolean
}

export interface KnowledgeProvenanceProjection {
  required: boolean
  available?: boolean
  status: string
  blockers: WorkflowBlocker[]
  source_references: KnowledgeSourceReferenceProjection[]
}

export interface WorkflowNextAction {
  action_id: string
  type: string
  target_step: string
  label: string
  reason: string
  required: boolean
  enabled: boolean
  blocked_by: string[]
}

export interface WorkflowReadiness {
  status: string
  blockers: WorkflowBlocker[]
  reasons: string[]
  next_required_actions: WorkflowNextAction[]
}

export interface FormalExportEligibility {
  eligible: boolean
  status: string
  blockers: WorkflowBlocker[]
  authority_owner: string
  revalidation_required: boolean
}

export interface AgentAssistanceProjection {
  available: boolean
  status: string
  blocking_core_workflow: boolean
  capability_state: string
  route_exposure?: string
  unavailability_reason?: string
  active_provider?: string
  active_model?: string
}

export interface WorkflowProjectContext {
  project_id: string
  project_code: string
  project_name: string
  project_version_id: string
  project_version_number: number
  project_version_status: string
  revision_stale: boolean
  revision_stale_reasons: string[]
  revision_freshness: string
}

export interface WorkflowAggregateV1 {
  contract_version: string
  generated_at: string
  project_context: WorkflowProjectContext
  current_step: string
  workflow_status: string
  workflow_goal: string
  steps: Array<{
    step: string
    applicability: string
    status: string
    blocking: boolean
    blockers: WorkflowBlocker[]
  }>
  blockers: WorkflowBlocker[]
  primary_action_id: string
  next_required_actions: WorkflowNextAction[]
  workflow_readiness: WorkflowReadiness
  formal_export_eligibility: FormalExportEligibility
  agent_assistance: AgentAssistanceProjection
  knowledge_provenance?: KnowledgeProvenanceProjection
}
