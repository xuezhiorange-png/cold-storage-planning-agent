export const CANONICAL_STAGE_ORDER = [
  'zone',
  'cooling_load',
  'equipment',
  'power',
  'investment'
] as const

export type CanonicalStageName = (typeof CANONICAL_STAGE_ORDER)[number]

export const CANONICAL_CALCULATOR_NAMES = {
  zone: 'cold_room_zone_plan',
  cooling_load: 'cooling_load',
  equipment: 'equipment',
  power: 'installed_power',
  investment: 'investment_estimate'
} as const satisfies Record<CanonicalStageName, string>

export const SUPPLEMENTAL_POWER_CONFIGURATION = 'power_configuration'

export const STAGE_LABELS: Record<CanonicalStageName, string> = {
  zone: '区域规划',
  cooling_load: '冷负荷',
  equipment: '设备选型',
  power: '装机功率',
  investment: '投资估算'
}

export const CALCULATOR_TO_STAGE: Record<string, CanonicalStageName> = {
  [CANONICAL_CALCULATOR_NAMES.zone]: 'zone',
  [CANONICAL_CALCULATOR_NAMES.cooling_load]: 'cooling_load',
  [CANONICAL_CALCULATOR_NAMES.equipment]: 'equipment',
  [CANONICAL_CALCULATOR_NAMES.power]: 'power',
  [CANONICAL_CALCULATOR_NAMES.investment]: 'investment'
}

export const STAGE_UPSTREAM_STAGES: Record<CanonicalStageName, CanonicalStageName[]> = {
  zone: [],
  cooling_load: ['zone'],
  equipment: ['cooling_load'],
  power: ['equipment'],
  investment: ['zone', 'power']
}
