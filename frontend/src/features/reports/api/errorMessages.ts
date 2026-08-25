import { isApiError } from '../../../api/errors'
import type { ReportBlocker } from '../types'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function readString(record: Record<string, unknown> | null, key: string): string | null {
  const value = record?.[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function isReportBlocker(value: unknown): value is ReportBlocker {
  const record = asRecord(value)
  return Boolean(readString(record, 'code') && readString(record, 'message'))
}

/**
 * Extract structured blockers from an API error payload when the backend
 * includes them (e.g. QualityBlockerError details). Never invents codes.
 */
export function extractBlockersFromError(error: unknown): ReportBlocker[] {
  if (!isApiError(error)) return []

  const candidates: unknown[] = []
  const details = error.details

  if (Array.isArray(details)) {
    candidates.push(...details)
  } else {
    const record = asRecord(details)
    if (record) {
      if (Array.isArray(record.blockers)) candidates.push(...record.blockers)
      const nested = asRecord(record.detail)
      if (nested && Array.isArray(nested.blockers)) candidates.push(...nested.blockers)
    }
  }

  return candidates.filter(isReportBlocker)
}

/**
 * Format an API or transport error for display. Preserves backend messages.
 */
export function formatReportError(error: unknown, fallback: string): string {
  if (isApiError(error)) {
    const blockers = extractBlockersFromError(error)
    if (blockers.length > 0) {
      return blockers.map((b) => `${b.code}: ${b.message}`).join('; ')
    }
    return error.message || fallback
  }
  return error instanceof Error ? error.message : fallback
}
