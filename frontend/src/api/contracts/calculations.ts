export interface PersistedFormulaEntry {
  formula_id?: string
  formula_version?: string
  expression?: string
  description?: string
}

export interface CalculationResultSnapshot {
  success: boolean
  calculator_name: string
  calculator_version: string
  input: Record<string, unknown>
  result: Record<string, unknown>
  formulas?: PersistedFormulaEntry[]
}

export interface CalculationRunRecord {
  id: string
  calculation_id?: string
  project_id: string
  project_version_id: string
  calculator_name: string
  calculator_version: string
  input_snapshot?: Record<string, unknown>
  result_snapshot: CalculationResultSnapshot | Record<string, unknown>
  result_hash?: string
  upstream_calculation_ids?: Record<string, string>
  formulas?: PersistedFormulaEntry[]
  coefficients?: unknown[]
  assumptions?: string[]
  warnings?: unknown[]
  source_references?: unknown[]
  requires_review: boolean
}
