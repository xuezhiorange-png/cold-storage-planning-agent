export type ReportLocale = 'zh-CN' | 'en-US'
export type ExportFormat = 'docx' | 'pdf'
export type RenderMode = 'draft' | 'formal'
export type ArtifactStatus = 'pending' | 'rendering' | 'completed' | 'failed'
export type ReportStatus =
  | 'draft'
  | 'generated'
  | 'under_review'
  | 'reviewed'
  | 'approved'
  | 'archived'

export interface ReportListItemContract {
  id: string
  status: ReportStatus
}

export interface ListReportsResponse {
  reports: ReportListItemContract[]
}

export interface ReportDetailResponse {
  id: string
  status: ReportStatus
  revision_number: number
}

export interface RevisionListItemContract {
  revision_number: number
  content_hash: string
}

export interface ListRevisionsResponse {
  revisions: RevisionListItemContract[]
}

export interface RenderReportRequest {
  format: ExportFormat
  template_version?: string | null
  mode: RenderMode
  idempotency_key?: string | null
  locale: ReportLocale
}

export interface ArtifactResponse {
  artifact_id: string
  status: ArtifactStatus
  format: ExportFormat
  file_name: string
  file_size_bytes: number
  file_sha256: string
  locale: ReportLocale
  template_locale: ReportLocale
  translation_catalog_version: string
  translation_catalog_content_hash: string
  localized_template_content_hash: string
}

export interface ArtifactListItemContract {
  artifact_id: string
  status: ArtifactStatus
  format: ExportFormat
  file_name: string
  file_size_bytes: number
  revision_number: number
  generated_at: string
  locale: ReportLocale
  template_locale: ReportLocale
  translation_catalog_version: string
  translation_catalog_content_hash: string
  localized_template_content_hash: string
}

export interface ListExportsResponse {
  exports: ArtifactListItemContract[]
}

export interface ArtifactDetailResponse extends ArtifactListItemContract {
  file_sha256: string
  template_version: string
}

export interface ArtifactDownload {
  blob: Blob
  artifactId: string
  fileName: string
  contentSha256: string
  sourceContentHash: string
  templateVersion: string
  locale: ReportLocale
  templateLocale: ReportLocale
  translationCatalogVersion: string
  translationCatalogContentHash: string
  localizedTemplateContentHash: string
}
