export interface PersistedColumnDef {
  key: string
  label: string
  unit?: string
}

export interface PersistedScalarField {
  label: string
  key: string
  unit: string
}

const AISLE_LAYOUT_LABELS: Record<string, string> = {
  three_side_3m: '三面通道',
  'three_side_2.2m': '三面通道',
  one_long_side_3m: '单侧长边通道',
  four_side_architectural: '四边通道'
}

const SCHEME_ID_LABELS: Record<string, string> = {
  '6_position': '6位间',
  '8_position': '8位间'
}

const EQUIPMENT_AREA_LABELS: Record<string, string> = {
  machine_room: '机房'
}

export function formatAisleLayout(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const text = String(value).trim()
  if (!text) return '—'
  return AISLE_LAYOUT_LABELS[text] ?? text
}

export function formatSchemeId(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const text = String(value).trim()
  if (!text) return '—'
  return SCHEME_ID_LABELS[text] ?? text
}

export function formatEquipmentArea(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const text = String(value).trim()
  if (!text) return '—'
  return EQUIPMENT_AREA_LABELS[text] ?? text
}

export const COOLING_LOAD_SCALAR_FIELDS: PersistedScalarField[] = [
  { label: '总冷负荷', key: 'total_cooling_load_kw', unit: 'kW(r)' },
  { label: '安全裕量负荷', key: 'safety_margin_load_kw', unit: 'kW(r)' },
  { label: '围护结构传热负荷', key: 'envelope_heat_transfer_load_kw', unit: 'kW(r)' },
  { label: '产品显热负荷', key: 'product_sensible_heat_load_kw', unit: 'kW(r)' },
  { label: '包装负荷', key: 'packaging_load_kw', unit: 'kW(r)' },
  { label: '渗透负荷', key: 'infiltration_load_kw', unit: 'kW(r)' },
  { label: '人员负荷', key: 'personnel_load_kw', unit: 'kW(r)' },
  { label: '照明负荷', key: 'lighting_load_kw', unit: 'kW(r)' },
  { label: '蒸发风机负荷', key: 'evaporator_fan_load_kw', unit: 'kW(r)' },
  { label: '化霜附加负荷', key: 'defrost_additional_load_kw', unit: 'kW(r)' },
  { label: '其他配置负荷', key: 'other_configuration_load_kw', unit: 'kW(r)' }
]

export const COOLING_ZONE_COLUMNS: PersistedColumnDef[] = [
  { key: 'zone_code', label: '区域编码' },
  { key: 'zone_name', label: '区域名称' },
  { key: 'temperature_level', label: '温区等级' },
  { key: 'room_design_temperature', label: '室内设计温度', unit: '°C' },
  { key: 'room_height', label: '层高', unit: 'm' },
  { key: 'transmission_load_kw_r', label: '传热负荷', unit: 'kW(r)' },
  { key: 'product_load_kw_r', label: '产品负荷', unit: 'kW(r)' },
  { key: 'infiltration_load_kw_r', label: '渗透负荷', unit: 'kW(r)' },
  { key: 'internal_load_kw_r', label: '内部负荷', unit: 'kW(r)' },
  { key: 'defrost_load_kw_r', label: '化霜负荷', unit: 'kW(r)' },
  { key: 'subtotal_load_kw_r', label: '小计冷负荷', unit: 'kW(r)' }
]

export const COOLING_LEVEL_SUMMARY_COLUMNS: PersistedColumnDef[] = [
  { key: 'temperature_level_code', label: '温区等级' },
  { key: 'room_count', label: '间数' },
  { key: 'subtotal_load_kw_r', label: '小计冷负荷', unit: 'kW(r)' },
  { key: 'diversified_load_kw_r', label: '折算冷负荷', unit: 'kW(r)' },
  { key: 'zones', label: '包含区域' }
]

export const EQUIPMENT_SCALAR_FIELDS: PersistedScalarField[] = [
  { label: '蒸发器总制冷量', key: 'evaporator_total_cooling_capacity_kw', unit: 'kW' },
  { label: '蒸发器数量', key: 'evaporator_quantity', unit: '' },
  { label: '单台蒸发器容量', key: 'single_evaporator_capacity_kw', unit: 'kW' },
  { label: '压缩机运行容量', key: 'compressor_operating_capacity_kw', unit: 'kW' },
  { label: '备用容量', key: 'standby_capacity_kw', unit: 'kW' },
  { label: '冷凝器散热量', key: 'condenser_heat_rejection_capacity_kw', unit: 'kW' },
  { label: '蒸发温度', key: 'evaporation_temperature_c', unit: '℃' },
  { label: '冷凝温度', key: 'condensing_temperature_c', unit: '℃' },
  { label: '化霜方式', key: 'defrost_method', unit: '' }
]

export const EQUIPMENT_SYSTEM_COLUMNS: PersistedColumnDef[] = [
  { key: 'system_code', label: '系统编码' },
  { key: 'system_name', label: '系统名称' },
  { key: 'design_evaporating_temperature_c', label: '设计蒸发温度', unit: '℃' },
  { key: 'system_simultaneous_load_kw_r', label: '系统同时负荷', unit: 'kW(r)' },
  { key: 'evaporator_total_capacity_kw_r', label: '蒸发器总容量', unit: 'kW(r)' },
  { key: 'evaporator_count', label: '蒸发器数量' },
  { key: 'evaporator_quantity', label: '蒸发器台数' },
  { key: 'single_evaporator_capacity_kw_r', label: '单台蒸发器容量', unit: 'kW(r)' },
  { key: 'compressor_operating_capacity_kw_r', label: '压缩机运行容量', unit: 'kW(r)' },
  { key: 'compressor_installed_capacity_kw_r', label: '压缩机装机容量', unit: 'kW(r)' },
  { key: 'compressor_standby_capacity_kw_r', label: '备用容量', unit: 'kW(r)' },
  { key: 'compressor_input_power_kw_e', label: '压缩机输入功率', unit: 'kW(e)' },
  { key: 'condenser_heat_rejection_kw', label: '冷凝器散热量', unit: 'kW' }
]

export const INSTALLED_POWER_SCALAR_FIELDS: PersistedScalarField[] = [
  { label: '装机总功率', key: 'total_installed_power_kw_e', unit: 'kW(e)' },
  { label: '估算需求功率', key: 'total_estimated_demand_kw', unit: 'kW' }
]

export const POWER_EQUIPMENT_ROW_COLUMNS: PersistedColumnDef[] = [
  { key: 'sequence', label: '序号' },
  { key: 'name', label: '设备名称' },
  { key: 'area', label: '所属区域' },
  { key: 'quantity', label: '数量' },
  { key: 'defrost_power_kw', label: '化霜功率', unit: 'kW' },
  { key: 'defrost_total_power_kw', label: '化霜总功率', unit: 'kW' },
  { key: 'running_power_kw', label: '运行功率', unit: 'kW' },
  { key: 'total_power_kw', label: '总功率', unit: 'kW' },
  { key: 'section', label: '分项' }
]

export const POWER_SUMMARY_ROW_COLUMNS: PersistedColumnDef[] = [
  { key: 'name', label: '汇总项' },
  { key: 'basis', label: '依据' },
  { key: 'total_power_kw', label: '总功率', unit: 'kW' }
]

export const POWER_ITEM_COLUMNS: PersistedColumnDef[] = [
  { key: 'category', label: '类别' },
  { key: 'installed_power_kw', label: '装机功率', unit: 'kW' },
  { key: 'demand_factor', label: '需用系数' },
  { key: 'estimated_demand_kw', label: '估算需用功率', unit: 'kW' }
]

export const INVESTMENT_ITEM_COLUMNS: PersistedColumnDef[] = [
  { key: 'item_name', label: '投资分项' },
  { key: 'amount_cny', label: '估算金额' }
]
