import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import {
  CALCULATOR_TO_STAGE,
  CANONICAL_CALCULATOR_NAMES,
  CANONICAL_STAGE_ORDER,
  STAGE_LABELS,
  STAGE_UPSTREAM_STAGES,
  type CanonicalStageName
} from './canonicalCalculators'

export type FiveStageSlotStatus =
  | 'missing'
  | 'present'
  | 'partial'
  | 'stale'
  | 'locked'
  | 'error'

export interface FiveStageSlotView {
  stage: CanonicalStageName
  label: string
  calculatorName: string
  status: FiveStageSlotStatus
  record: CalculationRunRecord | null
  calculationId: string | null
  resultHash: string | null
  requiresReview: boolean
  warnings: string[]
  upstreamCalculationIds: Record<string, string> | null
  staleReasons: string[]
}

export interface FiveStageProgressView {
  slots: FiveStageSlotView[]
  completedCount: number
  totalCount: number
  chainComplete: boolean
  hasPartialChain: boolean
  overallRequiresReview: boolean
  supplementalPowerConfiguration: CalculationRunRecord | null
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

function latestByCalculatorName(
  records: CalculationRunRecord[]
): Record<string, CalculationRunRecord> {
  const latest: Record<string, CalculationRunRecord> = {}
  for (const record of records) {
    if (record.calculator_name) {
      latest[record.calculator_name] = record
    }
  }
  return latest
}

function readUpstreamIds(record: CalculationRunRecord | undefined): Record<string, string> | null {
  const upstream = record?.upstream_calculation_ids
  if (!upstream || typeof upstream !== 'object') return null
  const normalized: Record<string, string> = {}
  for (const [key, value] of Object.entries(upstream)) {
    if (typeof value === 'string') {
      normalized[key] = value
    }
  }
  return Object.keys(normalized).length > 0 ? normalized : null
}

function recordCalculationId(record: CalculationRunRecord | null): string | null {
  if (!record) return null
  return record.calculation_id ?? record.id ?? null
}

function detectStaleReasons(
  record: CalculationRunRecord,
  byCalculator: Record<string, CalculationRunRecord>,
  stage: CanonicalStageName
): string[] {
  const upstreamStages = STAGE_UPSTREAM_STAGES[stage]
  const upstreamIds = readUpstreamIds(record)
  if (!upstreamIds) return []

  const reasons: string[] = []
  for (const upstreamStage of upstreamStages) {
    const upstreamCalculator = CANONICAL_CALCULATOR_NAMES[upstreamStage]
    const upstreamRecord = byCalculator[upstreamCalculator]
    const expectedId = upstreamIds[upstreamStage] ?? upstreamIds[upstreamCalculator]
    const actualId = recordCalculationId(upstreamRecord)
    if (expectedId && actualId && expectedId !== actualId) {
      reasons.push(`${STAGE_LABELS[upstreamStage]} 计算结果已更新`)
    }
    const expectedHash = upstreamRecord?.result_hash
    const boundHash = upstreamIds[`${upstreamStage}_result_hash`]
    if (expectedHash && boundHash && expectedHash !== boundHash) {
      reasons.push(`${STAGE_LABELS[upstreamStage]} 结果哈希不匹配`)
    }
  }
  return reasons
}

function slotStatus(
  record: CalculationRunRecord | null,
  staleReasons: string[],
  versionLocked: boolean
): FiveStageSlotStatus {
  if (versionLocked) return 'locked'
  if (!record) return 'missing'
  if (staleReasons.length > 0) return 'stale'
  if (record.result_snapshot?.success === false) return 'error'
  return 'present'
}

export function mapFiveStageProgress(
  records: CalculationRunRecord[],
  options: { versionLocked?: boolean } = {}
): FiveStageProgressView {
  const byCalculator = latestByCalculatorName(records)
  const versionLocked = options.versionLocked ?? false

  const slots: FiveStageSlotView[] = CANONICAL_STAGE_ORDER.map((stage) => {
    const calculatorName = CANONICAL_CALCULATOR_NAMES[stage]
    const record = byCalculator[calculatorName] ?? null
    const staleReasons = record ? detectStaleReasons(record, byCalculator, stage) : []
    const warnings = asStringArray(record?.warnings)

    return {
      stage,
      label: STAGE_LABELS[stage],
      calculatorName,
      status: slotStatus(record, staleReasons, versionLocked && !record),
      record,
      calculationId: recordCalculationId(record),
      resultHash: record?.result_hash ?? null,
      requiresReview: Boolean(record?.requires_review),
      warnings,
      upstreamCalculationIds: readUpstreamIds(record ?? undefined),
      staleReasons
    }
  })

  const presentSlots = slots.filter((slot) => slot.record !== null)
  const completedCount = presentSlots.length
  const chainComplete = completedCount === CANONICAL_STAGE_ORDER.length
  const hasPartialChain = completedCount > 0 && !chainComplete
  const overallRequiresReview = slots.some((slot) => slot.requiresReview)

  if (hasPartialChain) {
    for (const slot of slots) {
      if (!slot.record) {
        slot.status = versionLocked ? 'locked' : 'partial'
      }
    }
  }

  return {
    slots,
    completedCount,
    totalCount: CANONICAL_STAGE_ORDER.length,
    chainComplete,
    hasPartialChain,
    overallRequiresReview,
    supplementalPowerConfiguration: byCalculator.power_configuration ?? null
  }
}

export function isVersionLocked(status: string | null | undefined): boolean {
  const normalized = (status ?? '').toLowerCase()
  return normalized === 'approved' || normalized === 'archived'
}

export { CALCULATOR_TO_STAGE }
