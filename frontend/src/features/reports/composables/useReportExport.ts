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
 * Wires together:
 *   - ReportsApi for all HTTP calls
 *   - LatestRequestGate to cancel stale in-flight requests
 *   - Browser download triggering via a temporary <a> element
 */
export function useReportExport(api: ReportsApi = reportsApi) {
  const gate = new LatestRequestGate()

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
   * Stale requests from previous calls are auto-aborted.
   */
  async function loadReports(projectId?: string): Promise<void> {
    const handle = gate.begin()
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
   * Uses a single shared gate handle so the parallel calls don't abort each other.
   */
  async function selectReport(reportId: string): Promise<void> {
    const handle = gate.begin()

    selectedReportId.value = reportId
    selectedRevisionNumber.value = null
    renderResult.value = null
    exports.value = []

    revisionsLoading.value = true
    revisionsError.value = ''
    exportsLoading.value = true
    exportsError.value = ''

    try {
      const [revResponse, expResponse] = await Promise.all([
        api.listRevisions(reportId, handle.signal),
        api.listExports(reportId, undefined, handle.signal)
      ])

      if (handle.isCurrent()) {
        revisions.value = revResponse.revisions
        exports.value = expResponse.exports
      }
    } catch (err: unknown) {
      if (!isStale(err, handle)) {
        // Determine which operation failed based on the error context
        revisionsError.value = extractMessage(err, '加载版本列表失败')
        exportsError.value = extractMessage(err, '加载导出列表失败')
      }
    } finally {
      if (handle.isCurrent()) {
        revisionsLoading.value = false
        exportsLoading.value = false
      }
      handle.finish()
    }
  }

  /**
   * Load revision history for a given report.
   */
  async function loadRevisions(reportId: string): Promise<void> {
    const handle = gate.begin()
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
   * Refreshes the exports list on success so the new artifact appears immediately.
   */
  async function renderReport(
    reportId: string,
    revisionNumber: number,
    form: ExportForm
  ): Promise<void> {
    const handle = gate.begin()
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
        handle.finish() // release the gate before the refresh call

        // Refresh exports so the caller sees the newly created artifact
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
    const handle = gate.begin()
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
    const handle = gate.begin()
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
   * Reset all state and cancel any in-flight requests.
   */
  function reset(): void {
    gate.cancel()

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
