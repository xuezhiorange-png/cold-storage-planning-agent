import { describe, expect, it, vi } from 'vitest'

import type { HttpClient } from '../../../src/api/httpClient'
import { createReportsApi, type ReportsApi } from '../../../src/features/reports/api/reportsApi'
import { useReportExport } from '../../../src/features/reports/composables/useReportExport'

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

describe('useReportExport persisted revision content', () => {
  it('loadRevisionContent exposes project_summary and scheme_comparison from export JSON', async () => {
    const c = createClient()
    const mockJson = c.requestJson as ReturnType<typeof vi.fn>

    mockJson.mockResolvedValueOnce({
      content: {
        project_summary: {
          project_name: 'V0.7 信任闭环操作员示例项目',
          location: '山东'
        },
        scheme_comparison: {
          review_authority: {
            scheme_run_id: 'run-1',
            source_binding_id: 'binding-1',
            combined_source_hash: 'hash-abc'
          }
        }
      }
    })

    const api = createMockApi(c)
    const ctx = useReportExport(api)

    await ctx.loadRevisionContent('report-1', 1)

    expect(mockJson).toHaveBeenCalledWith(
      '/api/v1/reports/report-1/export?revision_number=1&format=json',
      expect.any(Object)
    )
    expect(ctx.revisionContent.value?.project_summary?.project_name).toBe(
      'V0.7 信任闭环操作员示例项目'
    )
    expect(ctx.revisionContent.value?.scheme_comparison?.review_authority?.scheme_run_id).toBe(
      'run-1'
    )
  })
})
