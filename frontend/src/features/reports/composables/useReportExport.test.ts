import { describe, expect, it, vi } from 'vitest'

import type { HttpClient } from '../../../api/httpClient'
import { createReportsApi, type ReportsApi } from '../api/reportsApi'
import {
  createDefaultExportForm,
  useReportExport
} from './useReportExport'

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

function createClient(): HttpClient {
  return {
    requestJson: vi.fn(),
    requestBlob: vi.fn(),
    requestBinary: vi.fn()
  }
}

function createMockApi(client: HttpClient): ReportsApi {
  return createReportsApi(client)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useReportExport', () => {
  /* ── Initial state ─────────────────────────────────────────── */

  it('starts with empty / idle state', () => {
    const c = createClient()
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    expect(ctx.reports.value).toEqual([])
    expect(ctx.reportsLoading.value).toBe(false)
    expect(ctx.reportsError.value).toBe('')

    expect(ctx.selectedReportId.value).toBeNull()
    expect(ctx.selectedRevisionNumber.value).toBeNull()
    expect(ctx.selectedReport.value).toBeNull()

    expect(ctx.revisions.value).toEqual([])
    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.revisionsError.value).toBe('')

    expect(ctx.exports.value).toEqual([])
    expect(ctx.exportsLoading.value).toBe(false)
    expect(ctx.exportsError.value).toBe('')

    expect(ctx.renderLoading.value).toBe(false)
    expect(ctx.renderError.value).toBe('')
    expect(ctx.renderResult.value).toBeNull()

    expect(ctx.downloadLoading.value).toBe(false)
    expect(ctx.downloadError.value).toBe('')
    expect(ctx.downloadResult.value).toBeNull()
  })

  /* ── loadReports ───────────────────────────────────────────── */

  it('loadReports populates the reports list', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockResolvedValue({
      reports: [
        { id: 'r1', status: 'draft' },
        { id: 'r2', status: 'generated' }
      ]
    })
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.loadReports()

    expect(ctx.reports.value).toHaveLength(2)
    expect(ctx.reports.value[0].id).toBe('r1')
    expect(ctx.reports.value[1].status).toBe('generated')
    expect(ctx.reportsLoading.value).toBe(false)
    expect(ctx.reportsError.value).toBe('')
  })

  it('loadReports sets error on failure', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(new Error('Network failure'))
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.loadReports()

    expect(ctx.reports.value).toEqual([])
    expect(ctx.reportsError.value).toBe('Network failure')
    expect(ctx.reportsLoading.value).toBe(false)
  })

  it('loadReports ignores stale responses', async () => {
    const c = createClient()

    let firstResolve!: (v: unknown) => void
    const firstPromise = new Promise((resolve) => {
      firstResolve = resolve
    })
    vi.mocked(c.requestJson).mockImplementation(
      () => firstPromise as Promise<unknown>
    )

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Start first request
    const firstDone = ctx.loadReports()

    // Start second request (this will abort the first)
    vi.mocked(c.requestJson).mockResolvedValue({
      reports: [{ id: 'r2', status: 'generated' }]
    })
    await ctx.loadReports()

    // Now resolve the first (stale) one
    firstResolve({ reports: [{ id: 'r1', status: 'draft' }] })
    await firstDone

    // The composable should have ignored the stale response
    expect(ctx.reports.value).toHaveLength(1)
    expect(ctx.reports.value[0].id).toBe('r2')
  })

  /* ── selectReport ──────────────────────────────────────────── */

  it('selectReport loads revisions and exports for the report', async () => {
    const c = createClient()
    // selectReport now calls listRevisions and listExports with the same AbortSignal
    // so we use mockImplementationOnce to return different results per call
    vi.mocked(c.requestJson)
      .mockResolvedValueOnce({
        revisions: [
          { revision_number: 1, content_hash: 'abc' },
          { revision_number: 2, content_hash: 'def' }
        ]
      })
      .mockResolvedValueOnce({
        exports: [
          {
            artifact_id: 'a1',
            status: 'completed',
            format: 'pdf',
            file_name: 'r.pdf',
            file_size_bytes: 100,
            revision_number: 1,
            generated_at: '2026-06-26T00:00:00Z',
            locale: 'zh-CN',
            template_locale: 'zh-CN',
            translation_catalog_version: '1',
            translation_catalog_content_hash: 'ch',
            localized_template_content_hash: 'lh'
          }
        ]
      })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.selectReport('r1')

    expect(ctx.selectedReportId.value).toBe('r1')
    expect(ctx.revisions.value).toHaveLength(2)
    expect(ctx.revisions.value[0].revision_number).toBe(1)
    expect(ctx.exports.value).toHaveLength(1)
    expect(ctx.exports.value[0].artifact_id).toBe('a1')
    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.exportsLoading.value).toBe(false)
  })

  /* ── renderReport ──────────────────────────────────────────── */

  it('renderReport calls the API with the correct payload', async () => {
    const c = createClient()

    // Cast needed because mockImplementation works with the implementation type
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>
    mockJson
      // render response
      .mockResolvedValueOnce({
        artifact_id: 'new-artifact',
        status: 'pending',
        format: 'pdf',
        file_name: 'report.pdf',
        file_size_bytes: 0,
        file_sha256: '',
        locale: 'zh-CN',
        template_locale: 'zh-CN',
        translation_catalog_version: '1.0.0',
        translation_catalog_content_hash: 'ch',
        localized_template_content_hash: 'lh'
      })
      // subsequent loadExports response (called after render completes)
      .mockResolvedValueOnce({ exports: [] })

    const api = createMockApi(c)
    const ctx = useReportExport(api)
    const form = createDefaultExportForm()

    await ctx.renderReport('r1', 2, form)

    expect(ctx.renderResult.value?.artifact_id).toBe('new-artifact')
    expect(ctx.renderResult.value?.status).toBe('pending')
    expect(ctx.renderLoading.value).toBe(false)
    expect(ctx.renderError.value).toBe('')
    expect(ctx.selectedRevisionNumber.value).toBe(2)

    // Verify the render request body was passed
    expect(mockJson).toHaveBeenCalledWith(
      expect.stringContaining('/render'),
      expect.objectContaining({
        method: 'POST',
        body: expect.objectContaining({
          format: 'pdf',
          mode: 'draft',
          locale: 'zh-CN'
        })
      })
    )
  })

  it('renderReport sets error on failure', async () => {
    const c = createClient()
    vi.mocked(c.requestJson).mockRejectedValue(new Error('Render failed'))
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.renderReport('r1', 1, createDefaultExportForm())

    expect(ctx.renderError.value).toBe('Render failed')
    expect(ctx.renderLoading.value).toBe(false)
  })

  /* ── downloadArtifact ──────────────────────────────────────── */

  it('downloadArtifact calls download API and triggers browser download', async () => {
    const c = createClient()

    // jsdom does not implement URL.createObjectURL — provide stubs
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock') as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL

    vi.mocked(c.requestBinary).mockResolvedValue({
      blob: new Blob(['pdf-content']),
      status: 200,
      headers: new Headers({
        'Content-Disposition': "attachment; filename*=UTF-8''report.pdf",
        'X-Artifact-Id': 'a1',
        'X-Content-SHA256': 'sha',
        'X-Source-Content-Hash': 'src-hash',
        'X-Template-Version': '1.0',
        'X-Report-Locale': 'zh-CN',
        'X-Template-Locale': 'zh-CN',
        'X-Translation-Catalog-Version': '1',
        'X-Translation-Catalog-Content-Hash': 'ch',
        'X-Localized-Template-Content-Hash': 'lh'
      })
    })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.downloadArtifact('r1', 'a1')

    expect(ctx.downloadResult.value?.artifactId).toBe('a1')
    expect(ctx.downloadError.value).toBe('')
    expect(ctx.downloadLoading.value).toBe(false)

    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  })

  it('downloadArtifact sets error on failure', async () => {
    const c = createClient()
    vi.mocked(c.requestBinary).mockRejectedValue(new Error('Download failed'))
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.downloadArtifact('r1', 'a1')

    expect(ctx.downloadError.value).toBe('Download failed')
    expect(ctx.downloadLoading.value).toBe(false)
  })

  /* ── reset ─────────────────────────────────────────────────── */

  it('reset clears all state', () => {
    const c = createClient()
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Mutate state (cast needed due to DeepReadonly on other fields)
    ctx.reportsLoading.value = true
    ;(ctx as any).reportsError.value = 'err'
    ;(ctx as any).selectedReportId.value = 'xxx'
    ctx.renderLoading.value = true
    ;(ctx as any).renderError.value = 'prev'

    ctx.reset()

    expect(ctx.reportsLoading.value).toBe(false)
    expect(ctx.reportsError.value).toBe('')
    expect(ctx.selectedReportId.value).toBeNull()
    expect(ctx.renderLoading.value).toBe(false)
    expect(ctx.renderError.value).toBe('')
    expect(ctx.renderResult.value).toBeNull()
  })

  /* ── createDefaultExportForm ───────────────────────────────── */

  it('createDefaultExportForm returns sensible defaults', () => {
    const form = createDefaultExportForm()

    expect(form.format).toBe('pdf')
    expect(form.mode).toBe('draft')
    expect(form.locale).toBe('zh-CN')
    expect(form.templateVersion).toBeNull()
    expect(form.idempotencyKey).toBeNull()
  })
})
