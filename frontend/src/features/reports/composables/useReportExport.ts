import { computed, readonly, ref, type DeepReadonly, type Ref } from 'vue'

import type { ReportStatus } from '../../../api/contracts/reports'
import { LatestRequestGate } from '../../../shared/composables/latestRequestGate'
import { formatReportError, extractBlockersFromError } from '../api/errorMessages'
import { reportsApi, type ReportsApi } from '../api/reportsApi'

import type {
  ArtifactDownload,
  ArtifactListItemContract,
  ArtifactResponse,
  ExportFormat,
  RenderMode,
  ReportListItemContract,
  ReportLocale,
  RenderReportRequest
} from '../../../api/contracts/reports'
import type { ReportBlocker, ReportDetailState, ReportWorkflowContext, PersistedReportRevisionContent } from '../types'

/**
 * Mirrors backend DRAFT_EXPORT_STATUSES. Draft export does not require review.
 * Frontend must not add a review gate on this path.
 */
export const DRAFT_EXPORT_STATUSES: ReadonlySet<ReportStatus> = new Set([
  'draft',
  'generated',
  'under_review',
  'reviewed'
])

/**
 * Mirrors backend FORMAL_EXPORT_STATUSES. Formal export stays approved/archived
 * only. Do not weaken this set.
 */
export const FORMAL_EXPORT_STATUSES: ReadonlySet<ReportStatus> = new Set([
  'approved',
  'archived'
])

export const FORMAL_EXPORT_BLOCKER_CODE = 'FORMAL_EXPORT_BLOCKED'
export const FORMAL_REPORT_NOT_APPROVED_CODE = 'FORMAL_REPORT_NOT_APPROVED'

const FORMAL_PATH_BLOCKER_CODES: ReadonlySet<string> = new Set([
  FORMAL_EXPORT_BLOCKER_CODE,
  FORMAL_REPORT_NOT_APPROVED_CODE
])

/** Operator-visible policy: formal export stays gated. */
export const FORMAL_EXPORT_POLICY_COPY = '正式导出需要已批准/归档'

/** Operator-visible policy: draft export is independent of review. */
export const DRAFT_EXPORT_POLICY_COPY = '草稿导出不需要审核'

/**
 * Form values for initiating a report render/export.
 */
export interface ExportForm {
  format: ExportFormat
  mode: RenderMode
  locale: ReportLocale
  templateVersion: string | null
  idempotencyKey: string | null
}

/**
 * Creates a pristine export form with sensible defaults.
 */
export function createDefaultExportForm(): ExportForm {
  return {
    format: 'pdf',
    mode: 'draft',
    locale: 'zh-CN',
    templateVersion: null,
    idempotencyKey: null
  }
}

export function isDraftExportStatus(status: ReportStatus): boolean {
  return DRAFT_EXPORT_STATUSES.has(status)
}

export function isFormalExportStatus(status: ReportStatus): boolean {
  return FORMAL_EXPORT_STATUSES.has(status)
}

export function isFormalPathBlocker(blocker: { code: string }): boolean {
  return FORMAL_PATH_BLOCKER_CODES.has(blocker.code)
}

/**
 * Strip formal-only codes so they cannot become the draft-path error banner.
 */
export function filterDraftPathBlockers<T extends { code: string }>(
  blockers: readonly T[]
): T[] {
  return blockers.filter((blocker) => !isFormalPathBlocker(blocker))
}

/**
 * Format a render/download error for the active export mode.
 * Draft path must not present FORMAL_EXPORT_BLOCKED as its only/global error.
 */
export function formatExportError(
  error: unknown,
  fallback: string,
  mode: RenderMode
): string {
  const blockers = extractBlockersFromError(error)
  const relevant = mode === 'draft' ? filterDraftPathBlockers(blockers) : blockers
  if (relevant.length > 0) {
    return relevant.map((blocker) => `${blocker.code}: ${blocker.message}`).join('; ')
  }
  if (mode === 'draft' && blockers.length > 0) {
    return fallback
  }
  return formatReportError(error, fallback)
}

export interface DisplayedExportBlockersInput {
  mode: RenderMode
  actionBlockers: readonly ReportBlocker[]
  formalExportEligible: boolean
  formalExportBlockers: readonly ReportBlocker[]
}

function cloneBlocker(blocker: ReportBlocker): ReportBlocker {
  const cloned: ReportBlocker = {
    code: blocker.code,
    message: blocker.message
  }
  if (blocker.stage !== undefined) cloned.stage = blocker.stage
  if (blocker.source_type !== undefined) cloned.source_type = blocker.source_type
  if (blocker.source_id !== undefined) cloned.source_id = blocker.source_id
  if (blocker.severity !== undefined) cloned.severity = blocker.severity
  return cloned
}

/**
 * Draft path ignores formal eligibility. Formal blockers must not be copied
 * into the generic export banner while the operator is on draft mode.
 */
export function selectDisplayedExportBlockers(
  input: DisplayedExportBlockersInput
): ReportBlocker[] {
  if (input.mode === 'draft') {
    return filterDraftPathBlockers(input.actionBlockers).map(cloneBlocker)
  }

  const fromActions = input.actionBlockers.map(cloneBlocker)
  if (fromActions.length > 0) return fromActions
  if (!input.formalExportEligible) {
    return input.formalExportBlockers.map(cloneBlocker)
  }
  return []
}

/**
 * Reactive state and actions for the report-export feature.
 *
 * Uses four independent LatestRequestGate instances so that unrelated
 * domains (reports list, detail, render, download) never cancel each
 * other and stale responses cannot leave loading flags permanently true.
 *
 * Domains:
 *   - reportsGate  → loadReports
 *   - detailGate   → selectReport, loadRevisions, loadExports
 *   - renderGate   → renderReport
 *   - downloadGate → downloadArtifact
 */
export function useReportExport(api: ReportsApi = reportsApi) {
  /* ── 4 independent gate domains ──────────────────────────── */

  const reportsGate = new LatestRequestGate()
  const detailGate = new LatestRequestGate()
  const renderGate = new LatestRequestGate()
  const downloadGate = new LatestRequestGate()
  const workflowGate = new LatestRequestGate()
  const reviewGate = new LatestRequestGate()
  const revisionContentGate = new LatestRequestGate()

  /* ── Reports list ────────────────────────────────────────── */

  const reports = ref<ReportListItemContract[]>([])
  const reportsLoading = ref(false)
  const reportsError = ref('')

  /* ── Report detail (authoritative status from GET) ───────── */

  const reportDetail = ref<ReportDetailState | null>(null)
  const reportDetailLoading = ref(false)
  const reportDetailError = ref('')

  /* ── Create + generate workflow ──────────────────────────── */

  const createLoading = ref(false)
  const createError = ref('')
  const generateLoading = ref(false)
  const generateError = ref('')
  const actionBlockers = ref<ReportBlocker[]>([])

  /* ── Review workflow ─────────────────────────────────────── */

  const reviewLoading = ref(false)
  const reviewError = ref('')

  const revisions = ref<Array<{ revision_number: number; content_hash: string }>>([])
  const revisionsLoading = ref(false)
  const revisionsError = ref('')

  const revisionContent = ref<PersistedReportRevisionContent | null>(null)
  const revisionContentLoading = ref(false)
  const revisionContentError = ref('')

  /* ── Selected report / revision identity ─────────────────── */

  const selectedReportId = ref<string | null>(null)
  const selectedRevisionNumber = ref<number | null>(null)

  /** Convenience accessor for the full selected report item. */
  const selectedReport = computed<ReportListItemContract | null>(() => {
    const id = selectedReportId.value
    return id ? reports.value.find((r) => r.id === id) ?? null : null
  })

  /* ── Exports (artifacts) ─────────────────────────────────── */

  const exports = ref<ArtifactListItemContract[]>([])
  const exportsLoading = ref(false)
  const exportsError = ref('')

  /* ── Render action ───────────────────────────────────────── */

  const renderLoading = ref(false)
  const renderError = ref('')
  const renderResult = ref<ArtifactResponse | null>(null)

  /* ── Download action ─────────────────────────────────────── */

  const downloadLoading = ref(false)
  const downloadError = ref('')
  const downloadResult = ref<ArtifactDownload | null>(null)

  /* ── Actions ─────────────────────────────────────────────── */

  /**
   * Load all reports, optionally filtered by project.
   * Stale requests from previous calls are auto-aborted via reportsGate.
   */
  async function loadReports(projectId?: string): Promise<void> {
    const handle = reportsGate.begin()
    reportsLoading.value = true
    reportsError.value = ''

    try {
      const response = await api.list(projectId, handle.signal)
      if (handle.isCurrent()) {
        reports.value = response.reports
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        reportsError.value = formatReportError(err, '加载报告列表失败')
      }
    } finally {
      if (handle.isCurrent()) reportsLoading.value = false
      handle.finish()
    }
  }

  /**
   * Load authoritative report detail (status + current revision) from GET.
   */
  async function loadReportDetail(reportId: string): Promise<void> {
    const handle = detailGate.begin()
    reportDetailLoading.value = true
    reportDetailError.value = ''

    try {
      const response = await api.get(reportId, handle.signal)
      if (handle.isCurrent()) {
        reportDetail.value = {
          id: response.id,
          status: response.status,
          revision_number: response.revision_number
        }
        syncReportStatusInList(reportId, response.status)
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        reportDetailError.value = formatReportError(err, '加载报告详情失败')
      }
    } finally {
      if (handle.isCurrent()) reportDetailLoading.value = false
      handle.finish()
    }
  }

  function syncReportStatusInList(reportId: string, status: ReportStatus): void {
    const item = reports.value.find((r) => r.id === reportId)
    if (item) item.status = status
  }

  /**
   * Create a report for the current workbench project/version, then generate
   * the first revision. Does not call the legacy V0.4 planning helper API.
   */
  async function createAndGenerateReport(context: ReportWorkflowContext): Promise<string | null> {
    if (!context.projectId || !context.projectVersionId) {
      createError.value = '缺少项目或版本标识，无法创建报告'
      return null
    }

    const handle = workflowGate.begin()
    createLoading.value = true
    generateLoading.value = true
    createError.value = ''
    generateError.value = ''
    actionBlockers.value = []

    try {
      const created = await api.create(
        {
          project_id: context.projectId,
          project_version_id: context.projectVersionId,
          report_type: context.reportType ?? 'cold_storage_concept_design'
        },
        handle.signal
      )

      if (!handle.isCurrent()) return null

      createLoading.value = false

      const generated = await api.generate(created.report_id, undefined, handle.signal)

      if (!handle.isCurrent()) return null

      generateLoading.value = false

      await loadReports(context.projectId)
      await selectReport(created.report_id)
      await loadRevisionContent(created.report_id, generated.revision_number)
      reportDetail.value = {
        id: created.report_id,
        status: created.status,
        revision_number: generated.revision_number
      }
      syncReportStatusInList(created.report_id, created.status)

      return created.report_id
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        const blockers = extractBlockersFromError(err)
        if (blockers.length > 0) {
          actionBlockers.value = blockers
        }
        const message = formatReportError(err, '创建或生成报告失败')
        if (createLoading.value) {
          createError.value = message
        } else {
          generateError.value = message
        }
      }
      return null
    } finally {
      if (handle.isCurrent()) {
        createLoading.value = false
        generateLoading.value = false
      }
      handle.finish()
    }
  }

  /**
   * Generate a new revision for an existing report.
   */
  async function generateRevision(reportId: string): Promise<boolean> {
    const handle = workflowGate.begin()
    generateLoading.value = true
    generateError.value = ''
    actionBlockers.value = []

    try {
      const generated = await api.generate(reportId, undefined, handle.signal)
      if (handle.isCurrent()) {
        if (reportDetail.value?.id === reportId) {
          reportDetail.value = {
            ...reportDetail.value,
            revision_number: generated.revision_number
          }
        }
        await loadRevisions(reportId)
        await loadReportDetail(reportId)
        if (reportDetail.value?.revision_number) {
          await loadRevisionContent(reportId, reportDetail.value.revision_number)
        }
        return true
      }
      return false
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        const blockers = extractBlockersFromError(err)
        if (blockers.length > 0) actionBlockers.value = blockers
        generateError.value = formatReportError(err, '生成报告版本失败')
      }
      return false
    } finally {
      if (handle.isCurrent()) generateLoading.value = false
      handle.finish()
    }
  }

  async function submitReview(reportId: string, comment = ''): Promise<boolean> {
    return runReviewAction('submitReview', reportId, comment)
  }

  async function markReviewed(reportId: string, comment = ''): Promise<boolean> {
    return runReviewAction('markReviewed', reportId, comment)
  }

  async function approveReport(reportId: string, comment = ''): Promise<boolean> {
    return runReviewAction('approve', reportId, comment)
  }

  async function runReviewAction(
    method: 'submitReview' | 'markReviewed' | 'approve',
    reportId: string,
    comment: string
  ): Promise<boolean> {
    const handle = reviewGate.begin()
    reviewLoading.value = true
    reviewError.value = ''
    actionBlockers.value = []

    try {
      const response = await api[method](reportId, { comment }, handle.signal)
      if (handle.isCurrent()) {
        syncReportStatusInList(reportId, response.status)
        if (reportDetail.value?.id === reportId) {
          reportDetail.value = { ...reportDetail.value, status: response.status }
        }
        await loadReportDetail(reportId)
        return true
      }
      return false
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        // Review failures stay in reviewError. Browser mark_reviewed fail-closes
        // (actor is system) and must not become the default "cannot export" banner.
        reviewError.value = formatReportError(err, '审核操作请求失败')
      }
      return false
    } finally {
      if (handle.isCurrent()) reviewLoading.value = false
      handle.finish()
    }
  }

  /**
   * Select a report and load its revisions + exports in parallel.
   *
   * Uses Promise.allSettled so one failing request does not discard the
   * other's successful result.  Each domain gets its own error slot.
   * Stale responses (from a newer selectReport call) are silently ignored.
   */
  async function selectReport(reportId: string): Promise<void> {
    const handle = detailGate.begin()

    selectedReportId.value = reportId
    selectedRevisionNumber.value = null
    renderResult.value = null
    exports.value = []
    reportDetail.value = null
    revisionContent.value = null

    revisionsLoading.value = true
    revisionsError.value = ''
    exportsLoading.value = true
    exportsError.value = ''

    const [revResult, expResult, detailResult] = await Promise.allSettled([
      api.listRevisions(reportId, handle.signal),
      api.listExports(reportId, undefined, handle.signal),
      api.get(reportId, handle.signal)
    ])

    if (handle.isCurrent()) {
      if (revResult.status === 'fulfilled') {
        revisions.value = revResult.value.revisions
      } else if (!isStale(revResult.reason, handle)) {
        revisionsError.value = formatReportError(revResult.reason, '加载版本列表失败')
      }

      if (expResult.status === 'fulfilled') {
        exports.value = expResult.value.exports
      } else if (!isStale(expResult.reason, handle)) {
        exportsError.value = formatReportError(expResult.reason, '加载导出列表失败')
      }

      if (detailResult.status === 'fulfilled') {
        reportDetail.value = {
          id: detailResult.value.id,
          status: detailResult.value.status,
          revision_number: detailResult.value.revision_number
        }
        syncReportStatusInList(reportId, detailResult.value.status)
        if (detailResult.value.revision_number > 0) {
          await loadRevisionContent(reportId, detailResult.value.revision_number)
        }
      } else if (!isStale(detailResult.reason, handle)) {
        reportDetailError.value = formatReportError(detailResult.reason, '加载报告详情失败')
      }

      revisionsLoading.value = false
      exportsLoading.value = false
    }

    handle.finish()
  }

  async function loadRevisionContent(reportId: string, revisionNumber: number): Promise<void> {
    const handle = revisionContentGate.begin()
    revisionContentLoading.value = true
    revisionContentError.value = ''

    try {
      const exported = await api.exportJson(reportId, revisionNumber, handle.signal)
      if (handle.isCurrent()) {
        const content = (exported.content ?? exported) as PersistedReportRevisionContent
        revisionContent.value = content
        selectedRevisionNumber.value = revisionNumber
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        revisionContentError.value = formatReportError(err, '加载报告 JSON 内容失败')
        revisionContent.value = null
      }
    } finally {
      if (handle.isCurrent()) revisionContentLoading.value = false
      handle.finish()
    }
  }

  /**
   * Load revision history for a given report.
   */
  async function loadRevisions(reportId: string): Promise<void> {
    const handle = detailGate.begin()
    revisionsLoading.value = true
    revisionsError.value = ''

    try {
      const response = await api.listRevisions(reportId, handle.signal)
      if (handle.isCurrent()) {
        revisions.value = response.revisions
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        revisionsError.value = formatReportError(err, '加载版本列表失败')
      }
    } finally {
      if (handle.isCurrent()) revisionsLoading.value = false
      handle.finish()
    }
  }

  /**
   * Render (export) a specific revision of a report.
   *
   * After the render call succeeds the renderGate handle is released
   * *before* the exports list refresh (which runs on detailGate).
   * This prevents a concurrent refresh from being cancelled if a new
   * render call arrives.
   */
  async function renderReport(
    reportId: string,
    revisionNumber: number,
    form: ExportForm
  ): Promise<void> {
    const handle = renderGate.begin()
    const reportIdAtCallTime = reportId
    renderLoading.value = true
    renderError.value = ''
    renderResult.value = null

    try {
      const body: RenderReportRequest = {
        format: form.format,
        mode: form.mode,
        locale: form.locale,
        template_version: form.templateVersion || null,
        idempotency_key: form.idempotencyKey || null
      }
      const response = await api.render(reportId, revisionNumber, body, handle.signal)

      if (handle.isCurrent()) {
        // Identity check: if the user selected a different report while this
        // render was in-flight, discard the result so we don't clobber B's state.
        if (selectedReportId.value !== null && selectedReportId.value !== reportIdAtCallTime) return

        renderResult.value = response
        selectedRevisionNumber.value = revisionNumber
        renderLoading.value = false
        handle.finish() // release renderGate before refresh

        // Double-check identity before loadExports — render may have resolved
        // after a selectReport call updated selectedReportId.
        if (selectedReportId.value !== null && selectedReportId.value !== reportIdAtCallTime) return

        // Refresh exports so the caller sees the newly created artifact.
        // This runs on the independent detailGate domain.
        await loadExports(reportId)
        return
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        const blockers = extractBlockersFromError(err)
        if (form.mode === 'draft') {
          actionBlockers.value = filterDraftPathBlockers(blockers)
        } else if (blockers.length > 0) {
          actionBlockers.value = blockers
        }
        renderError.value = formatExportError(err, '渲染报告失败', form.mode)
      }
    } finally {
      if (handle.isCurrent()) renderLoading.value = false
      handle.finish()
    }
  }

  /**
   * Load the list of exports (artifacts) for a report, optionally filtered by locale.
   */
  async function loadExports(reportId: string, locale?: ReportLocale): Promise<void> {
    const handle = detailGate.begin()
    exportsLoading.value = true
    exportsError.value = ''

    try {
      const response = await api.listExports(reportId, locale, handle.signal)
      if (handle.isCurrent()) {
        exports.value = response.exports
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        exportsError.value = formatReportError(err, '加载导出列表失败')
      }
    } finally {
      if (handle.isCurrent()) exportsLoading.value = false
      handle.finish()
    }
  }

  /**
   * Download an artifact and trigger a browser file-save.
   */
  async function downloadArtifact(reportId: string, artifactId: string): Promise<void> {
    const handle = downloadGate.begin()
    downloadLoading.value = true
    downloadError.value = ''
    downloadResult.value = null

    try {
      const response = await api.download(reportId, artifactId, handle.signal)

      if (handle.isCurrent()) {
        downloadResult.value = response
        triggerBrowserDownload(response)
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        downloadError.value = formatReportError(err, '下载文件失败')
      }
    } finally {
      if (handle.isCurrent()) downloadLoading.value = false
      handle.finish()
    }
  }

  /**
   * Reset all state and cancel any in-flight requests across all four gates.
   */
  function reset(): void {
    reportsGate.cancel()
    detailGate.cancel()
    renderGate.cancel()
    downloadGate.cancel()
    workflowGate.cancel()
    reviewGate.cancel()

    reports.value = []
    reportsLoading.value = false
    reportsError.value = ''

    reportDetail.value = null
    reportDetailLoading.value = false
    reportDetailError.value = ''

    createLoading.value = false
    createError.value = ''
    generateLoading.value = false
    generateError.value = ''
    actionBlockers.value = []

    reviewLoading.value = false
    reviewError.value = ''

    selectedReportId.value = null
    selectedRevisionNumber.value = null

    revisions.value = []
    revisionsLoading.value = false
    revisionsError.value = ''

    revisionContent.value = null
    revisionContentLoading.value = false
    revisionContentError.value = ''

    exports.value = []
    exportsLoading.value = false
    exportsError.value = ''

    renderLoading.value = false
    renderError.value = ''
    renderResult.value = null

    downloadLoading.value = false
    downloadError.value = ''
    downloadResult.value = null
  }

  return {
    /* state */
    reports: readonly(reports) as DeepReadonly<Ref<ReportListItemContract[]>>,
    reportsLoading,
    reportsError,

    reportDetail: readonly(reportDetail) as DeepReadonly<Ref<ReportDetailState | null>>,
    reportDetailLoading,
    reportDetailError,

    createLoading,
    createError,
    generateLoading,
    generateError,
    actionBlockers: readonly(actionBlockers) as DeepReadonly<Ref<ReportBlocker[]>>,

    reviewLoading,
    reviewError,

    selectedReportId,
    selectedRevisionNumber,
    selectedReport,

    revisions: readonly(revisions) as DeepReadonly<Ref<Array<{ revision_number: number; content_hash: string }>>>,
    revisionsLoading,
    revisionsError,

    revisionContent: readonly(revisionContent) as DeepReadonly<Ref<PersistedReportRevisionContent | null>>,
    revisionContentLoading,
    revisionContentError,

    exports: readonly(exports) as DeepReadonly<Ref<ArtifactListItemContract[]>>,
    exportsLoading,
    exportsError,

    renderLoading,
    renderError,
    renderResult: readonly(renderResult) as DeepReadonly<Ref<ArtifactResponse | null>>,

    downloadLoading,
    downloadError,
    downloadResult: readonly(downloadResult) as DeepReadonly<Ref<ArtifactDownload | null>>,

    /* actions */
    loadReports,
    loadReportDetail,
    createAndGenerateReport,
    generateRevision,
    submitReview,
    markReviewed,
    approveReport,
    selectReport,
    loadRevisions,
    loadRevisionContent,
    renderReport,
    loadExports,
    downloadArtifact,
    reset
  }
}

/* ── Helpers (module-private) ──────────────────────────────────── */

/**
 * Returns `true` when the error is an `AbortError` from a stale request.
 */
function isStale(err: unknown, handle: { isCurrent(): boolean }): boolean {
  return (
    !handle.isCurrent() ||
    (err instanceof DOMException && err.name === 'AbortError')
  )
}

/**
 * Create a temporary <a> element, click it to trigger the browser download,
 * then clean up.
 */
function triggerBrowserDownload(download: ArtifactDownload): void {
  const url = URL.createObjectURL(download.blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = download.fileName
  anchor.rel = 'noopener noreferrer'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
