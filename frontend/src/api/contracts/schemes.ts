export interface SchemeItemContract {
  scheme_code: string
  scheme_name: string
  feasible: boolean
  total_score: string
  total_area_m2: number | null
  total_position_count: number | null
  room_module_count: number | null
  door_count: number | null
  investment_cny: number | null
  installed_power_kw_e: number | null
  requires_review: boolean
}

export interface SchemeComparisonResponse {
  schemes: SchemeItemContract[]
  recommended_scheme_code: string | null
  weight_set_name: string
  weight_set_status: string
}
