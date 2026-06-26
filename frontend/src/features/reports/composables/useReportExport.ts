import { computed, readonly, ref, type DeepReadonly, type Ref } from 'vue'

import { LatestRequestGate } from '../../../shared/composables/latestRequestGate'
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

  /* ── Reports list ────────────────────────────────────────── */

  const reports = ref<ReportListItemContract[]>([])
  const reportsLoading = ref(false)
  const reportsError = ref('')

  /* ── Revision list for the selected report ───────────────── */

  const revisions = ref<Array<{ revision_number: number; content_hash: string }>>([])
  const revisionsLoading = ref(false)
  const revisionsError = ref('')

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
        reportsError.value = extractMessage(err, '加载报告列表失败')
      }
    } finally {
      if (handle.isCurrent()) reportsLoading.value = false
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

    revisionsLoading.value = true
    revisionsError.value = ''
    exportsLoading.value = true
    exportsError.value = ''

    const [revResult, expResult] = await Promise.allSettled([
      api.listRevisions(reportId, handle.signal),
      api.listExports(reportId, undefined, handle.signal)
    ])

    if (handle.isCurrent()) {
      if (revResult.status === 'fulfilled') {
        revisions.value = revResult.value.revisions
      } else if (!isStale(revResult.reason, handle)) {
        revisionsError.value = extractMessage(revResult.reason, '加载版本列表失败')
      }

      if (expResult.status === 'fulfilled') {
        exports.value = expResult.value.exports
      } else if (!isStale(expResult.reason, handle)) {
        exportsError.value = extractMessage(expResult.reason, '加载导出列表失败')
      }

      revisionsLoading.value = false
      exportsLoading.value = false
    }

    handle.finish()
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
        revisionsError.value = extractMessage(err, '加载版本列表失败')
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
        renderResult.value = response
        selectedRevisionNumber.value = revisionNumber
        renderLoading.value = false
        handle.finish() // release renderGate before refresh

        // Refresh exports so the caller sees the newly created artifact.
        // This runs on the independent detailGate domain.
        await loadExports(reportId)
        return
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        renderError.value = extractMessage(err, '渲染报告失败')
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
        exportsError.value = extractMessage(err, '加载导出列表失败')
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
        downloadError.value = extractMessage(err, '下载文件失败')
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

    reports.value = []
    reportsLoading.value = false
    reportsError.value = ''

    selectedReportId.value = null
    selectedRevisionNumber.value = null

    revisions.value = []
    revisionsLoading.value = false
    revisionsError.value = ''

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

    selectedReportId,
    selectedRevisionNumber,
    selectedReport,

    revisions: readonly(revisions) as DeepReadonly<Ref<Array<{ revision_number: number; content_hash: string }>>>,
    revisionsLoading,
    revisionsError,

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
    selectReport,
    loadRevisions,
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
 * Safely extract an error message, falling back to a generic string.
 */
function extractMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
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
