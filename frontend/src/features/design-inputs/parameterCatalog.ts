import type { DesignParameter } from '../../types/design'
import { operatorDemoZoneLeaf, operatorDemoZoneValue } from './operatorDemoDefaults'

export const demoParameters: DesignParameter[] = [
  {
    key: 'daily_inbound_mass_kg',
    label: '日入库量',
    value: operatorDemoZoneValue('daily_inbound_mass_kg'),
    unit: operatorDemoZoneLeaf('daily_inbound_mass_kg').unit,
    state: 'confirmed'
  },
  { key: 'working_time_h_per_day', label: '每日工作时间', value: '16', unit: 'h/day', state: 'confirmed' },
  {
    key: 'finished_storage_days',
    label: '成品库库存天数',
    value: operatorDemoZoneValue('finished_storage_days'),
    unit: operatorDemoZoneLeaf('finished_storage_days').unit,
    state: 'confirmed'
  },
  {
    key: 'frozen_storage_days',
    label: '冻果储存天数',
    value: operatorDemoZoneValue('frozen_storage_days'),
    unit: operatorDemoZoneLeaf('frozen_storage_days').unit,
    state: 'confirmed'
  },
  {
    key: 'main_packaging_storage_days',
    label: '主包材储存天数',
    value: operatorDemoZoneValue('main_packaging_storage_days'),
    unit: operatorDemoZoneLeaf('main_packaging_storage_days').unit,
    state: 'confirmed'
  },
  {
    key: 'auxiliary_packaging_storage_days',
    label: '辅包材储存天数',
    value: operatorDemoZoneValue('auxiliary_packaging_storage_days'),
    unit: operatorDemoZoneLeaf('auxiliary_packaging_storage_days').unit,
    state: 'confirmed'
  },
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
