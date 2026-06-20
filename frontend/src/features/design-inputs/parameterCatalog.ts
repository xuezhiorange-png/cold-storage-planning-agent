import type { DesignParameter } from '../../types/design'

export const demoParameters: DesignParameter[] = [
  { key: 'daily_inbound_mass_kg', label: '日入库量', value: '25000', unit: 'kg/day', state: 'confirmed' },
  { key: 'working_time_h_per_day', label: '每日工作时间', value: '16', unit: 'h/day', state: 'confirmed' },
  { key: 'finished_storage_days', label: '成品库库存天数', value: '2.5', unit: 'day', state: 'confirmed' },
  { key: 'effective_volume_loading_kg_m3', label: '单位有效容积储量', value: '280', unit: 'kg/m3', state: 'review' },
  { key: 'room_design_temperature_c', label: '冷间设计温度', value: '', unit: '°C', state: 'missing' }
]

export const stateLabels: Record<DesignParameter['state'], string> = {
  confirmed: '用户确认值',
  calculated: '系统计算值',
  default: '默认值',
  tentative: '暂定值',
  review: '待复核值',
  invalid: '无效参数',
  missing: '缺失参数'
}
