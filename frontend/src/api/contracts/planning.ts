export interface PlanningRunRequest {
  daily_inbound_mass_kg: number
  working_time_h_per_day: number
  utilization_factor: number
  finished_storage_days: number
  packaging_storage_days: number
  main_packaging_storage_days: number
  auxiliary_packaging_storage_days: number
  reserve_factor: number
  precooling_required_ratio: number
  primary_precooling_working_hours_per_day: number
  secondary_precooling_working_hours_per_day: number
  raw_storage_ratio: number
  finished_goods_pallet_weight_kg: number
  frozen_fruit_ratio: number
  frozen_storage_days: number
  frozen_goods_pallet_weight_kg: number
}

export interface ZoneResultContract {
  zone_name: string
  temperature_band: string
  daily_throughput_kg_day?: number
  daily_throughput_kg?: number
  design_storage_mass_kg: number
  position_count: number
  required_area_m2: number
}

export interface InvestmentItemContract {
  item_name: string
  amount_cny: number
}

export interface EquipmentPowerRowContract {
  sequence: number
  name: string
  area: string
  quantity: number
  defrost_power_kw: number | null
  defrost_total_power_kw: number | null
  running_power_kw: number
  total_power_kw: number
}

export interface PowerSummaryRowContract {
  name: string
  basis: string
  total_power_kw: number
}

export interface PowerItemContract {
  category: string
  installed_power_kw: number
  demand_factor: number
  estimated_demand_kw: number
}

export interface PlanningRunResponse {
  success: boolean
  summary: {
    total_area_m2: number
    total_position_count: number
    total_investment_cny: number
    total_power_kw: number
    requires_review: boolean
  }
  zone_plan: {
    result: {
      zones: ZoneResultContract[]
    }
  }
  investment_estimate: {
    result: {
      items: InvestmentItemContract[]
    }
  }
  power_configuration: {
    equipment_rows: EquipmentPowerRowContract[]
    summary_rows: PowerSummaryRowContract[]
    items: PowerItemContract[]
    total_installed_power_kw: number
    total_estimated_demand_kw: number
    requires_review: boolean
  }
}
