export interface CalculationResultSnapshot {
  success: boolean
  calculator_name: string
  calculator_version: string
  input: Record<string, unknown>
  result: Record<string, unknown>
}

export interface CalculationRunRecord {
  id: string
  project_id: string
  project_version_id: string
  calculator_name: string
  calculator_version: string
  input_snapshot?: Record<string, unknown>
  result_snapshot: CalculationResultSnapshot
  formulas?: unknown[]
  coefficients?: unknown[]
  assumptions?: string[]
  warnings?: unknown[]
  source_references?: unknown[]
  requires_review: boolean
}
