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

/** Minimal artifact shape used throughout the tests. */
function makeExports(count: number, idPrefix = 'a'): Array<Record<string, unknown>> {
  const items: Array<Record<string, unknown>> = []
  for (let i = 1; i <= count; i++) {
    items.push({
      artifact_id: `${idPrefix}${i}`,
      status: 'completed',
      format: 'pdf',
      file_name: `${idPrefix}${i}.pdf`,
      file_size_bytes: i * 100,
      revision_number: 1,
      generated_at: '2026-06-26T00:00:00Z',
      locale: 'zh-CN',
      template_locale: 'zh-CN',
      translation_catalog_version: '1',
      translation_catalog_content_hash: 'ch',
      localized_template_content_hash: 'lh'
    })
  }
  return items
}

function makeRevisions(count: number, idPrefix = 'r'): Array<Record<string, unknown>> {
  const items: Array<Record<string, unknown>> = []
  for (let i = 1; i <= count; i++) {
    items.push({
      revision_number: i,
      content_hash: `${idPrefix}${i}`
    })
  }
  return items
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
        exports: makeExports(1, 'a')
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

  it('selectReport: revisions success + exports failure', async () => {
    const c = createClient()
    vi.mocked(c.requestJson)
      .mockResolvedValueOnce({
        revisions: makeRevisions(1, 'r')
      })
      .mockRejectedValueOnce(new Error('Export API unavailable'))

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.selectReport('r1')

    // Revisions succeeded
    expect(ctx.revisions.value).toHaveLength(1)
    expect(ctx.revisions.value[0].content_hash).toBe('r1')
    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.revisionsError.value).toBe('')

    // Exports failed — the error should be captured without affecting revisions
    expect(ctx.exports.value).toEqual([])
    expect(ctx.exportsLoading.value).toBe(false)
    expect(ctx.exportsError.value).toBe('Export API unavailable')
  })

  it('selectReport: exports success + revisions failure', async () => {
    const c = createClient()
    vi.mocked(c.requestJson)
      .mockRejectedValueOnce(new Error('Revisions API unavailable'))
      .mockResolvedValueOnce({
        exports: makeExports(2, 'x')
      })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.selectReport('r1')

    // Revisions failed
    expect(ctx.revisions.value).toEqual([])
    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.revisionsError.value).toBe('Revisions API unavailable')

    // Exports succeeded
    expect(ctx.exports.value).toHaveLength(2)
    expect(ctx.exports.value[0].artifact_id).toBe('x1')
    expect(ctx.exportsLoading.value).toBe(false)
    expect(ctx.exportsError.value).toBe('')
  })

  it('selectReport clears previous renderResult on new selection', async () => {
    const c = createClient()
    vi.mocked(c.requestJson)
      .mockResolvedValue({ revisions: [], exports: [] })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Simulate having a render result
    ;(ctx as any).renderResult.value = { artifact_id: 'old' }

    await ctx.selectReport('r1')

    expect(ctx.renderResult.value).toBeNull()
  })

  /* ── Quick-switch overlap protection ───────────────────────── */

  it('quick switch report A -> B, A response does not overwrite B', async () => {
    const c = createClient()

    // Deferred promises for A's two parallel requests
    let resolveARev!: (v: unknown) => void
    let resolveAExp!: (v: unknown) => void
    const promARev = new Promise((resolve) => {
      resolveARev = resolve
    })
    const promAExp = new Promise((resolve) => {
      resolveAExp = resolve
    })

    vi.mocked(c.requestJson)
      // A's calls — deferred
      .mockResolvedValueOnce(promARev as Promise<unknown>)
      .mockResolvedValueOnce(promAExp as Promise<unknown>)
      // B's calls — resolve immediately
      .mockResolvedValueOnce({
        revisions: makeRevisions(1, 'b')
      })
      .mockResolvedValueOnce({
        exports: makeExports(1, 'b')
      })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Start A (deferred promises — hangs)
    const promiseA = ctx.selectReport('A')

    // Start B — this aborts A via detailGate and resolves immediately
    await ctx.selectReport('B')

    // B's data is already in place
    expect(ctx.selectedReportId.value).toBe('B')
    expect(ctx.revisions.value).toHaveLength(1)
    expect(ctx.revisions.value[0].revision_number).toBe(1)
    expect(ctx.revisions.value[0].content_hash).toBe('b1')
    expect(ctx.exports.value).toHaveLength(1)
    expect(ctx.exports.value[0].artifact_id).toBe('b1')

    // Now resolve A's stale responses
    resolveARev({ revisions: makeRevisions(3, 'a') })
    resolveAExp({ exports: makeExports(3, 'a') })
    await promiseA

    // A's stale response must NOT have overwritten B's data
    expect(ctx.selectedReportId.value).toBe('B')
    expect(ctx.revisions.value).toHaveLength(1)
    expect(ctx.revisions.value[0].content_hash).toBe('b1')
    expect(ctx.exports.value).toHaveLength(1)
    expect(ctx.exports.value[0].artifact_id).toBe('b1')

    // Loading flags must be false
    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.exportsLoading.value).toBe(false)
  })

  /* ── Cross-domain independence ─────────────────────────────── */

  it('selectReport and downloadArtifact do not interfere', async () => {
    const c = createClient()

    // Deferred promises for selectReport
    let resolveRev!: (v: unknown) => void
    let resolveExp!: (v: unknown) => void
    const promRev = new Promise((resolve) => {
      resolveRev = resolve
    })
    const promExp = new Promise((resolve) => {
      resolveExp = resolve
    })

    vi.mocked(c.requestJson)
      .mockResolvedValueOnce(promRev as Promise<unknown>)
      .mockResolvedValueOnce(promExp as Promise<unknown>)

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Start selectReport (hangs)
    const selectCall = ctx.selectReport('r1')

    // While selectReport is in-flight, start a download (different gate)
    vi.mocked(c.requestBinary).mockResolvedValue({
      blob: new Blob(['content']),
      status: 200,
      headers: new Headers({
        'Content-Disposition': "attachment; filename*=UTF-8''report.pdf",
        'X-Artifact-Id': 'dl1',
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

    // Preserve URL stubs
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock') as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL

    await ctx.downloadArtifact('r1', 'dl1')

    // Download completes independently
    expect(ctx.downloadLoading.value).toBe(false)
    expect(ctx.downloadError.value).toBe('')
    expect(ctx.downloadResult.value?.artifactId).toBe('dl1')

    // selectReport is still loading (no stuck flags)
    expect(ctx.revisionsLoading.value).toBe(true)
    expect(ctx.exportsLoading.value).toBe(true)

    // Complete selectReport
    resolveRev({ revisions: makeRevisions(1, 'r') })
    resolveExp({ exports: makeExports(1, 'r') })
    await selectCall

    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.exportsLoading.value).toBe(false)
    expect(ctx.revisions.value).toHaveLength(1)

    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  })

  it('renderReport and loadReports can overlap without interference', async () => {
    const c = createClient()

    // Deferred promise for the render call
    let resolveRender!: (v: unknown) => void
    const promRender = new Promise((resolve) => {
      resolveRender = resolve
    })

    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    // #1: render call (deferred)
    mockJson.mockResolvedValueOnce(promRender)

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Start render (hangs at the render API call)
    const renderCall = ctx.renderReport('r1', 1, createDefaultExportForm())

    // Verify render is loading
    expect(ctx.renderLoading.value).toBe(true)

    // While render is in-flight, load reports (uses reportsGate — independent)
    mockJson
      // #2: loadReports
      .mockResolvedValueOnce({
        reports: [
          { id: 'r1', status: 'draft' },
          { id: 'r2', status: 'generated' }
        ]
      })
      // #3: exports refresh (called after render resolves)
      .mockResolvedValueOnce({ exports: [] })

    await ctx.loadReports()

    // Reports load independently
    expect(ctx.reports.value).toHaveLength(2)
    expect(ctx.reportsLoading.value).toBe(false)

    // Render must still be in-flight
    expect(ctx.renderLoading.value).toBe(true)

    // Complete the render
    resolveRender({
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
    await renderCall

    expect(ctx.renderLoading.value).toBe(false)
    expect(ctx.renderResult.value?.artifact_id).toBe('new-artifact')
    expect(ctx.selectedRevisionNumber.value).toBe(1)
  })

  it('render A resolves after selecting report B, does not affect B state', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    // Deferred promise for render A
    let resolveRenderA!: (v: unknown) => void
    const promRenderA = new Promise((resolve) => {
      resolveRenderA = resolve
    })

    // #1: render A (deferred)
    mockJson.mockResolvedValueOnce(promRenderA)

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Start render A (hangs at API call)
    const renderACall = ctx.renderReport('A', 1, createDefaultExportForm())
    expect(ctx.renderLoading.value).toBe(true)

    // Now select report B — uses detailGate (independent of renderGate),
    // so render A continues in background
    mockJson
      // #2: B's revisions
      .mockResolvedValueOnce({
        revisions: [{ revision_number: 1, content_hash: 'b1' }]
      })
      // #3: B's exports
      .mockResolvedValueOnce({
        exports: makeExports(1, 'b')
      })

    await ctx.selectReport('B')

    // B's state is fully set
    expect(ctx.selectedReportId.value).toBe('B')
    expect(ctx.selectedRevisionNumber.value).toBeNull()
    expect(ctx.renderResult.value).toBeNull()
    expect(ctx.revisions.value).toHaveLength(1)
    expect(ctx.revisions.value[0].content_hash).toBe('b1')
    expect(ctx.exports.value).toHaveLength(1)
    expect(ctx.exports.value[0].artifact_id).toBe('b1')

    // Now resolve render A — it should NOT overwrite B's state
    resolveRenderA({
      artifact_id: 'artifact-from-A',
      status: 'completed',
      format: 'pdf',
      file_name: 'a.pdf',
      file_size_bytes: 100,
      file_sha256: '',
      locale: 'zh-CN',
      template_locale: 'zh-CN',
      translation_catalog_version: '1.0.0',
      translation_catalog_content_hash: 'ch',
      localized_template_content_hash: 'lh'
    })

    // renderCall resolves but its result should have been discarded
    await renderACall

    // B's state must remain unchanged
    expect(ctx.selectedReportId.value).toBe('B')
    expect(ctx.selectedRevisionNumber.value).toBeNull()
    expect(ctx.renderResult.value).toBeNull()

    // B's revisions/exports must be intact
    expect(ctx.revisions.value).toHaveLength(1)
    expect(ctx.revisions.value[0].content_hash).toBe('b1')
    expect(ctx.exports.value).toHaveLength(1)
    expect(ctx.exports.value[0].artifact_id).toBe('b1')

    // Loading flags must be cleared (render finished)
    expect(ctx.renderLoading.value).toBe(false)
    expect(ctx.revisionsLoading.value).toBe(false)
    expect(ctx.exportsLoading.value).toBe(false)

    // Verify loadExports was NOT called for report A (only 3 calls:
    // render A, B revisions, B exports)
    expect(mockJson).toHaveBeenCalledTimes(3)
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

  it('reset cancels all in-flight requests — stale updates are ignored', async () => {
    const c = createClient()

    // Deferred promise so we can control when the reports request resolves
    let resolveReports!: (v: unknown) => void
    const promReports = new Promise((resolve) => {
      resolveReports = resolve
    })

    vi.mocked(c.requestJson).mockImplementation(
      () => promReports as Promise<unknown>
    )

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    // Start an in-flight request
    const reportsCall = ctx.loadReports()
    expect(ctx.reportsLoading.value).toBe(true)

    // Reset — cancels reportsGate (and all others)
    ctx.reset()

    // State is cleared immediately
    expect(ctx.reportsLoading.value).toBe(false)
    expect(ctx.reports.value).toEqual([])

    // Resolve the stale response
    resolveReports({ reports: [{ id: 'r1', status: 'draft' }] })
    await reportsCall

    // State must remain cleared — the stale response was discarded
    expect(ctx.reports.value).toEqual([])
    expect(ctx.reportsLoading.value).toBe(false)
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
