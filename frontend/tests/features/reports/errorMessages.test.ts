import { describe, expect, it } from 'vitest'

import { ApiError } from '../../../src/api/errors'
import { extractBlockersFromError, formatReportError } from '../../../src/features/reports/api/errorMessages'
import {
  DRAFT_EXPORT_POLICY_COPY,
  filterDraftPathBlockers,
  FORMAL_EXPORT_BLOCKER_CODE,
  FORMAL_EXPORT_POLICY_COPY,
  formatExportError
} from '../../../src/features/reports/composables/useReportExport'

describe('report errorMessages', () => {
  it('extracts blockers from ApiError details array', () => {
    const error = new ApiError({
      status: 422,
      message: 'Quality blockers present: 1',
      details: [{ code: 'MISSING_CANONICAL_SOURCE', message: 'Zone result missing' }]
    })

    expect(extractBlockersFromError(error)).toEqual([
      { code: 'MISSING_CANONICAL_SOURCE', message: 'Zone result missing' }
    ])
  })

  it('formats blocker messages without inventing codes', () => {
    const error = new ApiError({
      status: 409,
      message: 'Cannot export report',
      details: [{ code: 'FORMAL_EXPORT_BLOCKED', message: 'Not approved' }]
    })

    expect(formatReportError(error, 'fallback')).toBe('FORMAL_EXPORT_BLOCKED: Not approved')
  })

  it('falls back to ApiError message when no blockers', () => {
    const error = new ApiError({ status: 409, message: 'Export permission denied' })
    expect(formatReportError(error, 'fallback')).toBe('Export permission denied')
  })

  it('keeps FORMAL_EXPORT_BLOCKED as a formal-path error, not a draft-path error', () => {
    const error = new ApiError({
      status: 409,
      message: 'Cannot export report',
      details: [{ code: FORMAL_EXPORT_BLOCKER_CODE, message: 'Not approved' }]
    })

    expect(formatExportError(error, '渲染报告失败', 'formal')).toBe(
      'FORMAL_EXPORT_BLOCKED: Not approved'
    )
    expect(formatExportError(error, '渲染报告失败', 'draft')).toBe('渲染报告失败')
    expect(formatExportError(error, '渲染报告失败', 'draft')).not.toContain(
      FORMAL_EXPORT_BLOCKER_CODE
    )
    expect(filterDraftPathBlockers(extractBlockersFromError(error))).toEqual([])
  })

  it('does not inject FORMAL_EXPORT_BLOCKED into a draft-path quality error', () => {
    const error = new ApiError({
      status: 422,
      message: 'Quality blockers present: 1',
      details: [{ code: 'MISSING_CANONICAL_SOURCE', message: 'Zone result missing' }]
    })

    expect(formatExportError(error, 'fallback', 'draft')).toBe(
      'MISSING_CANONICAL_SOURCE: Zone result missing'
    )
    expect(formatExportError(error, 'fallback', 'draft')).not.toContain('FORMAL_EXPORT_BLOCKED')
    expect(`${FORMAL_EXPORT_POLICY_COPY}，${DRAFT_EXPORT_POLICY_COPY}`).toContain(
      '草稿导出不需要审核'
    )
  })
})
