import { describe, expect, it } from 'vitest'

import { ApiError } from '../../../src/api/errors'
import { extractBlockersFromError, formatReportError } from '../../../src/features/reports/api/errorMessages'

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
})
