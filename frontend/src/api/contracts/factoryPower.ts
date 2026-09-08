export interface FactoryPowerCanonicalDetail {
  equipment_or_zone: string
  basis: string
  configured_quantity: number
  unit_power_kw: string
  installed_power_kw: string
  pool: string
  simultaneity_factor: string
  coincident_power_kw: string
  display_label?: string
  pool_label?: string
}

export interface FactoryPowerCanonicalSummary {
  defrost_installed_power_kw: string
  defrost_coincident_power_kw: string
  other_installed_power_kw: string
  other_coincident_power_kw: string
  production_equipment_installed_power_kw: string
  production_equipment_coincident_power_kw: string
  total_installed_power_kw: string
  estimated_total_power_kw: string
}

export interface FactoryPowerCanonicalResult {
  schema_version: string
  result_kind: string
  success: boolean
  calculator: {
    id: string
    version: string
    identity: string
  }
  input_authority: Record<string, unknown>
  factory_area_band: string
  unit_semantics: Record<string, unknown>
  provenance: Record<string, unknown>
  assumptions: string[]
  review: {
    requires_review: boolean
    status: string
  }
  details: FactoryPowerCanonicalDetail[]
  summary: FactoryPowerCanonicalSummary
}

export interface FactoryPowerPresentation {
  schema_version: string
  source_calculator_id: string
  source_calculator_version: string
  source_calculator_identity: string
  canonical_result_hash: string
  factory_area_band: string
  unit_semantics: Record<string, unknown>
  review: Record<string, unknown>
  provenance: Record<string, unknown>
  assumptions: string[]
  details: FactoryPowerCanonicalDetail[]
  summary: FactoryPowerCanonicalSummary
}
