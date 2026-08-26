export type BundleLeafState = 'provided' | 'tentative' | 'missing'
export type BundleSourceType = 'user' | 'persisted' | 'coefficient' | 'demo'
export type BundleValidityStatus = 'verified' | 'unverified' | 'conflict'

export interface BundleLeaf<T = unknown> {
  value: T
  unit: string | null
  state: BundleLeafState
  source_type: BundleSourceType
  validity_status: BundleValidityStatus
  requires_review: boolean
}

export interface EngineeringInputBundleV1 {
  schema_id: string
  schema_version: string
  project_version_identity: Record<string, BundleLeaf>
  zone_planning_inputs: Record<string, BundleLeaf>
  cooling_load_inputs: {
    zones: Array<Record<string, BundleLeaf>>
    coefficients: BundleLeaf<Record<string, string>>
  }
  equipment_inputs: {
    condensing_temperature_c: BundleLeaf
    systems: Array<{
      system_code: BundleLeaf
      system_name: BundleLeaf
      design_evaporating_temperature: BundleLeaf
      zones: Array<Record<string, BundleLeaf>>
    }>
    coefficients: BundleLeaf<Record<string, string>>
  }
  installed_power_inputs: Record<string, BundleLeaf>
  investment_inputs: Record<string, BundleLeaf>
  coefficient_context: {
    coefficient_context_id: BundleLeaf
    approved_revision_ids: BundleLeaf<string[]>
    demo_coefficient_leaves: unknown[]
  }
  units_metadata: {
    leaf_unit_by_path: Record<string, string>
  }
  source_metadata: {
    input_group_provenance: Record<string, string>
  }
  review_metadata: {
    overall_requires_review: BundleLeaf<boolean>
    per_group_requires_review: Record<string, boolean>
  }
}

export interface OperatorProcessInputV1 {
  schema_id: 'OperatorProcessInputV1'
  schema_version: '1.0.0'
  zone_planning_inputs: {
    daily_inbound_mass_kg: BundleLeaf
    working_time_h_per_day: BundleLeaf
    finished_storage_days: BundleLeaf
    packaging_storage_days: BundleLeaf
    precooling_required_ratio: BundleLeaf
  }
}

export type FiveStageExecutionRequest =
  | {
      engineering_input_bundle: EngineeringInputBundleV1
      idempotency_key: string
    }
  | {
      operator_process_input: OperatorProcessInputV1
      idempotency_key: string
    }

export interface FiveStageExecutionSuccess {
  success: true
  idempotent_replay: boolean
  source_binding_id: string
  calculation_ids: Record<string, string>
  result_hashes: Record<string, string>
  requires_review: boolean
  canonical_calculator_names: string[]
}

export interface FiveStageExecutionErrorBody {
  error: {
    code: string
    message: string
    field_path: string
    details?: Record<string, unknown>
  }
}

export type FiveStageExecutionResponse = FiveStageExecutionSuccess | FiveStageExecutionErrorBody

export function isFiveStageExecutionError(
  response: FiveStageExecutionResponse
): response is FiveStageExecutionErrorBody {
  return 'error' in response && response.error !== undefined
}
