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
