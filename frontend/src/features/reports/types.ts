import type { ReportLocale, ReportStatus } from '../../api/contracts/reports'

/** Feature-local report type aligned with backend ReportType enum. */
export type ReportType = 'cold_storage_concept_design'

export interface CreateReportRequest {
  project_id: string
  project_version_id: string
  report_type?: ReportType
  idempotency_key?: string | null
}

export interface CreateReportResponse {
  report_id: string
  status: ReportStatus
}

export interface GenerateRevisionRequest {
  idempotency_key?: string | null
}

export interface GenerateRevisionResponse {
  revision_number: number
  content_hash: string
}

export interface ReviewActionRequest {
  comment?: string
}

export interface ReviewActionResponse {
  status: ReportStatus
}

export interface ReportJsonExportResponse {
  [key: string]: unknown
}

/** Backend workflow blocker shape when surfaced in error payloads. */
export interface ReportBlocker {
  code: string
  message: string
  stage?: string
  source_type?: string
  source_id?: string
  severity?: string
}

export interface ReportWorkflowContext {
  projectId: string
  projectVersionId: string
  reportType?: ReportType
}

export interface ReportDetailState {
  id: string
  status: ReportStatus
  revision_number: number
}

export interface PersistedProjectSummary {
  project_name?: string
  project_code?: string
  location?: string
  product_category?: string
  [key: string]: unknown
}

export interface PersistedSchemeReviewAuthority {
  scheme_run_id?: string
  source_binding_id?: string
  combined_source_hash?: string
  requires_review?: boolean
  review_reasons?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface PersistedSchemeComparison {
  review_authority?: PersistedSchemeReviewAuthority
  recommended_scheme?: Record<string, unknown> | null
  schemes?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface PersistedInputConditions {
  daily_inbound_mass_kg?: number
  finished_storage_days?: number
  frozen_storage_days?: number
  main_packaging_storage_days?: number
  auxiliary_packaging_storage_days?: number
  [key: string]: unknown
}

export interface PersistedCalculationLogicFormula {
  formula_id?: string
  formula_version?: string
  expression?: string
  description?: string
}

export interface PersistedCalculationLogicStage {
  stage?: string
  calculator_name?: string
  calculator_version?: string
  calculation_id?: string
  formulas?: PersistedCalculationLogicFormula[]
  [key: string]: unknown
}

export interface PersistedCalculationLogic {
  stages?: PersistedCalculationLogicStage[]
  [key: string]: unknown
}

export interface PersistedReportRevisionContent {
  project_summary?: PersistedProjectSummary
  input_conditions?: PersistedInputConditions
  calculation_logic?: PersistedCalculationLogic
  scheme_comparison?: PersistedSchemeComparison
  [key: string]: unknown
}
