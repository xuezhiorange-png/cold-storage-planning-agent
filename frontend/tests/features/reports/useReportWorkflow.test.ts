import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../src/api/errors'
import type { HttpClient } from '../../../src/api/httpClient'
import { createReportsApi, type ReportsApi } from '../../../src/features/reports/api/reportsApi'
import {
  createDefaultExportForm,
  DRAFT_EXPORT_POLICY_COPY,
  DRAFT_EXPORT_STATUSES,
  FORMAL_EXPORT_BLOCKER_CODE,
  FORMAL_EXPORT_POLICY_COPY,
  FORMAL_EXPORT_STATUSES,
  isDraftExportStatus,
  isFormalExportStatus,
  selectDisplayedExportBlockers,
  useReportExport
} from '../../../src/features/reports/composables/useReportExport'

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

describe('useReportExport guided workflow', () => {
  it('createAndGenerateReport calls create then generate without legacy planning helper API', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    mockJson
      .mockResolvedValueOnce({ report_id: 'report-new', status: 'draft' })
      .mockResolvedValueOnce({ revision_number: 1, content_hash: 'hash-1' })
      .mockResolvedValueOnce({ reports: [{ id: 'report-new', status: 'draft' }] })
      .mockResolvedValueOnce({ revisions: [{ revision_number: 1, content_hash: 'hash-1' }] })
      .mockResolvedValueOnce({ exports: [] })
      .mockResolvedValueOnce({
        id: 'report-new',
        status: 'draft',
        revision_number: 1
      })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    const reportId = await ctx.createAndGenerateReport({
      projectId: 'proj-1',
      projectVersionId: 'ver-1'
    })

    expect(reportId).toBe('report-new')
    expect(mockJson).toHaveBeenCalledWith(
      '/api/v1/reports',
      expect.objectContaining({
        method: 'POST',
        body: expect.objectContaining({
          project_id: 'proj-1',
          project_version_id: 'ver-1'
        })
      })
    )
    expect(mockJson).toHaveBeenCalledWith(
      '/api/v1/reports/report-new/generate',
      expect.objectContaining({ method: 'POST' })
    )

    const urls = mockJson.mock.calls.map((call) => call[0] as string)
    expect(urls.some((url) => url.includes('/planning-run'))).toBe(false)
  })

  it('createAndGenerateReport fails closed without project_version_id', async () => {
    const c = createClient()
    const api = createMockApi(c)
    const ctx = useReportExport(api)

    const reportId = await ctx.createAndGenerateReport({
      projectId: 'proj-1',
      projectVersionId: ''
    })

    expect(reportId).toBeNull()
    expect(ctx.createError.value).toContain('缺少项目或版本标识')
    expect(c.requestJson).not.toHaveBeenCalled()
  })

  it('renderReport surfaces formal export blockers from 409 ApiError', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    mockJson.mockRejectedValueOnce(
      new ApiError({
        status: 409,
        message: 'Cannot export report report-1 in formal mode',
        details: [{ code: 'FORMAL_EXPORT_BLOCKED', message: 'Report not approved' }]
      })
    )

    const api = createMockApi(c)
    const ctx = useReportExport(api)
    const form = createDefaultExportForm()
    form.mode = 'formal'

    await ctx.renderReport('report-1', 1, form)

    expect(ctx.renderError.value).toContain('FORMAL_EXPORT_BLOCKED')
    expect(ctx.actionBlockers.value).toEqual([
      { code: 'FORMAL_EXPORT_BLOCKED', message: 'Report not approved' }
    ])
  })

  it('renderReport passes locale and format selection to API', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    mockJson
      .mockResolvedValueOnce({
        artifact_id: 'artifact-1',
        status: 'completed',
        format: 'docx',
        file_name: 'report.docx',
        file_size_bytes: 100,
        file_sha256: 'sha',
        locale: 'en-US',
        template_locale: 'en-US',
        translation_catalog_version: '1.0.0',
        translation_catalog_content_hash: 'ch',
        localized_template_content_hash: 'lh'
      })
      .mockResolvedValueOnce({ exports: [] })

    const api = createMockApi(c)
    const ctx = useReportExport(api)
    const form = createDefaultExportForm()
    form.format = 'docx'
    form.locale = 'en-US'

    await ctx.renderReport('report-1', 1, form)

    expect(mockJson).toHaveBeenCalledWith(
      expect.stringContaining('/render'),
      expect.objectContaining({
        body: expect.objectContaining({
          format: 'docx',
          locale: 'en-US',
          mode: 'draft'
        })
      })
    )
  })

  it('downloadArtifact preserves integrity headers from API layer', async () => {
    const c = createClient()
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock') as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL

    vi.mocked(c.requestBinary).mockResolvedValue({
      blob: new Blob(['pdf']),
      status: 200,
      headers: new Headers({
        'Content-Disposition': "attachment; filename*=UTF-8''report.pdf",
        'X-Artifact-Id': 'artifact-1',
        'X-Content-SHA256': 'artifact-sha',
        'X-Source-Content-Hash': 'source-hash',
        'X-Template-Version': '2.0.0',
        'X-Report-Locale': 'zh-CN',
        'X-Template-Locale': 'zh-CN',
        'X-Translation-Catalog-Version': '1.0.0',
        'X-Translation-Catalog-Content-Hash': 'catalog-hash',
        'X-Localized-Template-Content-Hash': 'localized-hash'
      })
    })

    const api = createMockApi(c)
    const ctx = useReportExport(api)
    await ctx.downloadArtifact('report-1', 'artifact-1')

    expect(ctx.downloadResult.value).toMatchObject({
      artifactId: 'artifact-1',
      contentSha256: 'artifact-sha',
      sourceContentHash: 'source-hash',
      templateVersion: '2.0.0',
      locale: 'zh-CN',
      templateLocale: 'zh-CN'
    })

    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  })
})

describe('draft export independent of review (V0.9 P4)', () => {
  it('defaults export mode to draft and keeps FORMAL_EXPORT_STATUSES approved/archived only', () => {
    const form = createDefaultExportForm()
    expect(form.mode).toBe('draft')
    expect([...DRAFT_EXPORT_STATUSES].sort()).toEqual(
      ['draft', 'generated', 'reviewed', 'under_review'].sort()
    )
    expect([...FORMAL_EXPORT_STATUSES].sort()).toEqual(['approved', 'archived'].sort())
    expect(isDraftExportStatus('under_review')).toBe(true)
    expect(isDraftExportStatus('approved')).toBe(false)
    expect(isFormalExportStatus('approved')).toBe(true)
    expect(isFormalExportStatus('reviewed')).toBe(false)
    expect(`${FORMAL_EXPORT_POLICY_COPY}，${DRAFT_EXPORT_POLICY_COPY}`).toBe(
      '正式导出需要已批准/归档，草稿导出不需要审核'
    )
  })

  it('selectDisplayedExportBlockers ignores formal eligibility on the draft path', () => {
    const displayed = selectDisplayedExportBlockers({
      mode: 'draft',
      actionBlockers: [],
      formalExportEligible: false,
      formalExportBlockers: [
        { code: FORMAL_EXPORT_BLOCKER_CODE, message: 'Report not approved' },
        { code: 'FORMAL_REPORT_NOT_APPROVED', message: "Report status 'draft' is not formal-exportable" }
      ]
    })

    expect(displayed).toEqual([])
  })

  it('selectDisplayedExportBlockers strips FORMAL_EXPORT_BLOCKED from draft action blockers', () => {
    const displayed = selectDisplayedExportBlockers({
      mode: 'draft',
      actionBlockers: [
        { code: FORMAL_EXPORT_BLOCKER_CODE, message: 'Report not approved' },
        { code: 'MISSING_CANONICAL_SOURCE', message: 'Zone result missing' }
      ],
      formalExportEligible: false,
      formalExportBlockers: [{ code: FORMAL_EXPORT_BLOCKER_CODE, message: 'Report not approved' }]
    })

    expect(displayed).toEqual([
      { code: 'MISSING_CANONICAL_SOURCE', message: 'Zone result missing' }
    ])
  })

  it('selectDisplayedExportBlockers may show formal blockers only in formal mode', () => {
    const displayed = selectDisplayedExportBlockers({
      mode: 'formal',
      actionBlockers: [],
      formalExportEligible: false,
      formalExportBlockers: [
        { code: FORMAL_EXPORT_BLOCKER_CODE, message: 'Report not approved' }
      ]
    })

    expect(displayed).toEqual([
      { code: FORMAL_EXPORT_BLOCKER_CODE, message: 'Report not approved' }
    ])
  })

  it('renderReport in draft mode does not present FORMAL_EXPORT_BLOCKED as the draft-path error', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    mockJson.mockRejectedValueOnce(
      new ApiError({
        status: 409,
        message: 'Cannot export report report-1 in formal mode',
        details: [{ code: 'FORMAL_EXPORT_BLOCKED', message: 'Report not approved' }]
      })
    )

    const api = createMockApi(c)
    const ctx = useReportExport(api)
    const form = createDefaultExportForm()
    expect(form.mode).toBe('draft')

    await ctx.renderReport('report-1', 1, form)

    expect(ctx.renderError.value).not.toContain('FORMAL_EXPORT_BLOCKED')
    expect(ctx.actionBlockers.value).toEqual([])
    expect(mockJson).toHaveBeenCalledWith(
      expect.stringContaining('/render'),
      expect.objectContaining({
        body: expect.objectContaining({ mode: 'draft' })
      })
    )
  })

  it('markReviewed fail-closed does not populate export actionBlockers', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    mockJson.mockRejectedValueOnce(
      new ApiError({
        status: 403,
        message: 'Trusted operator required',
        details: [{ code: 'UNTRUSTED_OPERATOR', message: 'actor is system' }]
      })
    )

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    const ok = await ctx.markReviewed('report-1')

    expect(ok).toBe(false)
    expect(ctx.reviewError.value).toContain('UNTRUSTED_OPERATOR')
    expect(ctx.actionBlockers.value).toEqual([])
  })
})
