<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

interface ZoneResult {
  zone_name: string
  temperature_band: string
  daily_throughput_kg_day?: number
  daily_throughput_kg?: number
  design_storage_mass_kg: number
  position_count: number
  required_area_m2: number
}

interface InvestmentItem {
  item_name: string
  amount_cny: number
}

interface PlanningRunResponse {
  success: boolean
  summary: {
    total_area_m2: number
    total_position_count: number
    total_investment_cny: number
    total_power_kw: number
    requires_review: boolean
  }
  power_configuration: {
    equipment_rows: EquipmentPowerRow[]
    summary_rows: PowerSummaryRow[]
    items: PowerItem[]
    total_installed_power_kw: number
    total_estimated_demand_kw: number
    requires_review: boolean
  }
  zone_plan: {
    result: {
      zones: ZoneResult[]
    }
  }
  investment_estimate: {
    result: {
      items: InvestmentItem[]
    }
  }
}

interface PowerItem {
  category: string
  installed_power_kw: number
  demand_factor: number
  estimated_demand_kw: number
}

interface EquipmentPowerRow {
  sequence: number
  name: string
  area: string
  quantity: number
  defrost_power_kw: number | null
  defrost_total_power_kw: number | null
  running_power_kw: number
  total_power_kw: number
}

interface PowerSummaryRow {
  name: string
  basis: string
  total_power_kw: number
}

const activeView = ref('项目概览')
const isAgentOpen = ref(false)
const workflowSteps = [
  { label: '基本信息', view: '项目概览' },
  { label: '计算结果', view: '计算结果' },
  { label: '方案比选', view: '方案对比' },
  { label: '投资估算', view: '投资测算' },
  { label: '用电估算', view: '用电配置' },
  { label: '报告输出', view: '报告' }
]

const designInputs = reactive({
  dailyInboundMassTons: 25,
  workingHoursPerDay: 16,
  finishedStorageDays: 2.5,
  packagingStorageDays: 3,
  auxiliaryPackagingStorageDays: 30,
  precoolingRequiredRatio: 1,
  rawStorageRatio: 0.4,
  primaryPrecoolingWorkingHours: 6,
  secondaryPrecoolingWorkingHours: 16,
  finishedGoodsPalletWeightKg: 400,
  frozenFruitRatio: 0.1,
  frozenStorageDays: 5,
  frozenGoodsPalletWeightKg: 600
})
interface SchemeItem {
  scheme_code: string
  scheme_name: string
  feasible: boolean
  total_score: string
  total_area_m2: number
  total_position_count: number
  room_module_count: number
  door_count: number
  investment_cny: number
  installed_power_kw_e: number
  requires_review: boolean
}

interface SchemeComparisonResponse {
  schemes: SchemeItem[]
  recommended_scheme_code: string | null
  weight_set_name: string
  weight_set_status: string
}

const schemeComparisonData = ref<SchemeComparisonResponse | null>(null)
const schemeLoadError = ref('')

const planningStatus = ref('当前显示 25 吨/天演示规划')
const planningError = ref('')
const factoryOverview = reactive({
  factoryName: '蓝莓加工厂',
  plantingAreaMu: 1250,
  mainVarieties: '蓝莓'
})

const zoneRows = ref([
  {
    zoneName: '办公室',
    temperatureBand: '常温',
    dailyThroughput: '25000 kg/day',
    storageMass: '0 kg',
    positions: '0',
    area: '60.00 m²'
  },
  {
    zoneName: '更衣室',
    temperatureBand: '常温',
    dailyThroughput: '25000 kg/day',
    storageMass: '0 kg',
    positions: '0',
    area: '100.00 m²'
  },
  {
    zoneName: '一级预冷间',
    temperatureBand: '8~10℃',
    dailyThroughput: '25000 kg/day',
    storageMass: '按周转配置',
    positions: '24',
    area: '134.40 m²'
  },
  {
    zoneName: '二级预冷间',
    temperatureBand: '1~3℃',
    dailyThroughput: '25000 kg/day',
    storageMass: '按周转配置',
    positions: '8',
    area: '44.80 m²'
  },
  {
    zoneName: '原果暂存间',
    temperatureBand: '8~10℃',
    dailyThroughput: '30000 kg/day',
    storageMass: '10000 kg',
    positions: '46',
    area: '86.11 m²'
  },
  {
    zoneName: '分选包装间',
    temperatureBand: '8~10℃',
    dailyThroughput: '25000 kg/day',
    storageMass: '按周转配置',
    positions: '0',
    area: '693.00 m²'
  },
  {
    zoneName: '覆膜间',
    temperatureBand: '1~3℃',
    dailyThroughput: '25000 kg/day',
    storageMass: '按周转配置',
    positions: '0',
    area: '120.00 m²'
  },
  {
    zoneName: '成品间',
    temperatureBand: '1~3℃',
    dailyThroughput: '25000 kg/day',
    storageMass: '62500 kg',
    positions: '157',
    area: '293.90 m²'
  },
  {
    zoneName: '次果暂存间',
    temperatureBand: '8~10℃',
    dailyThroughput: '2500 kg/day',
    storageMass: '10000 kg',
    positions: '0',
    area: '31.45 m²'
  },
  {
    zoneName: '冻果间',
    temperatureBand: '-18℃',
    dailyThroughput: '2500 kg/day',
    storageMass: '12500 kg',
    positions: '21',
    area: '39.31 m²'
  },
  {
    zoneName: '包材库',
    temperatureBand: '常温',
    dailyThroughput: '25000 kg/day',
    storageMass: '0 kg',
    positions: '90',
    area: '210.60 m²'
  }
])

const totalZoneArea = ref('1813.57 m²')
const totalPositions = ref('346')
const investmentRows = ref([
  { itemName: '土建及钢结构', amount: '253.22 万元' },
  { itemName: '冷库制冷设备', amount: '253.90 万元' },
  { itemName: '高低压配电', amount: '87.92 万元' },
  { itemName: '住宿及生活区', amount: '0.00 万元' },
  { itemName: '监控及开厂物资', amount: '20.00 万元' }
])
const totalInvestment = ref('615.04 万元')
const powerRows = ref([
  { sequence: '1', name: '制冷压缩机组', area: '一级预冷、原果暂存间、分选间', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '297.60 kW', totalPower: '297.60 kW' },
  { sequence: '2', name: '制冷压缩机组', area: '二级预冷间、成品库、出货通道、覆膜间', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '209.60 kW', totalPower: '209.60 kW' },
  { sequence: '3', name: '制冷压缩机组', area: '成品双温库', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '27.50 kW', totalPower: '55 kW' },
  { sequence: '4', name: '制冷压缩机组', area: '次果暂存区', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '4.21 kW', totalPower: '4.21 kW' },
  { sequence: '5', name: '制冷压缩机组', area: '冻果间', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '29.40 kW', totalPower: '29.40 kW' },
  { sequence: '6', name: '冷风机', area: '原果暂存', quantity: '3', defrostPower: '4.90 kW', defrostTotal: '14.70 kW', runningPower: '0.75 kW', totalPower: '2.25 kW' },
  { sequence: '7', name: '冷风机', area: '一级预冷间', quantity: '12', defrostPower: '16 kW', defrostTotal: '192 kW', runningPower: '2.68 kW', totalPower: '32.16 kW' },
  { sequence: '8', name: '冷风机', area: '分选间', quantity: '14', defrostPower: '4.90 kW', defrostTotal: '68.60 kW', runningPower: '0.75 kW', totalPower: '10.50 kW' },
  { sequence: '9', name: '冷风机', area: '二级预冷间', quantity: '14', defrostPower: '21.60 kW', defrostTotal: '302.40 kW', runningPower: '2.68 kW', totalPower: '37.52 kW' },
  { sequence: '10', name: '冷风机', area: '覆膜间', quantity: '3', defrostPower: '21.60 kW', defrostTotal: '64.80 kW', runningPower: '1.80 kW', totalPower: '5.39 kW' },
  { sequence: '11', name: '冷风机', area: '双温成品库', quantity: '4', defrostPower: '25.20 kW', defrostTotal: '100.80 kW', runningPower: '2.68 kW', totalPower: '10.72 kW' },
  { sequence: '12', name: '冷风机', area: '成品库', quantity: '3', defrostPower: '10 kW', defrostTotal: '30 kW', runningPower: '1.80 kW', totalPower: '5.39 kW' },
  { sequence: '13', name: '冷风机', area: '次果暂存间', quantity: '1', defrostPower: '8.50 kW', defrostTotal: '8.50 kW', runningPower: '1.35 kW', totalPower: '1.35 kW' },
  { sequence: '14', name: '冷风机', area: '冻果暂存间', quantity: '1', defrostPower: '31.50 kW', defrostTotal: '31.50 kW', runningPower: '3.20 kW', totalPower: '3.20 kW' },
  { sequence: '15', name: '冷风机', area: '出货通道', quantity: '2', defrostPower: '8.50 kW', defrostTotal: '17 kW', runningPower: '1.35 kW', totalPower: '2.69 kW' },
  { sequence: '16', name: '蒸发冷', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '28 kW', totalPower: '28 kW' },
  { sequence: '17', name: '蒸发冷', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '19 kW', totalPower: '19 kW' },
  { sequence: '18', name: '轴流风机', area: '-', quantity: '128', defrostPower: '-', defrostTotal: '-', runningPower: '0.55 kW', totalPower: '70.40 kW' },
  { sequence: '19', name: '升降平台', area: '-', quantity: '3', defrostPower: '-', defrostTotal: '-', runningPower: '2.20 kW', totalPower: '6.60 kW' },
  { sequence: '20', name: '工业滑升门', area: '-', quantity: '3', defrostPower: '-', defrostTotal: '-', runningPower: '0.40 kW', totalPower: '1.20 kW' },
  { sequence: '21', name: '充气门封', area: '-', quantity: '3', defrostPower: '-', defrostTotal: '-', runningPower: '0.40 kW', totalPower: '1.20 kW' },
  { sequence: '22', name: '电动门', area: '-', quantity: '29', defrostPower: '-', defrostTotal: '-', runningPower: '0.38 kW', totalPower: '11.02 kW' },
  { sequence: '23', name: '快卷门', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '0.38 kW', totalPower: '0.76 kW' },
  { sequence: '24', name: '风幕机', area: '-', quantity: '10', defrostPower: '-', defrostTotal: '-', runningPower: '0.38 kW', totalPower: '3.80 kW' },
  { sequence: '25', name: '冷库照明', area: '-', quantity: '350', defrostPower: '-', defrostTotal: '-', runningPower: '0.04 kW', totalPower: '14 kW' },
  { sequence: '26', name: '地坪加热丝', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '2 kW', totalPower: '2 kW' },
  { sequence: '27', name: '紫外线灯', area: '-', quantity: '190', defrostPower: '-', defrostTotal: '-', runningPower: '0.08 kW', totalPower: '15.20 kW' },
  { sequence: '28', name: '臭氧', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '15 kW', totalPower: '15 kW' },
  { sequence: '29', name: '加湿', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '15 kW', totalPower: '15 kW' },
  { sequence: '35', name: '折箱机', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '12 kW', totalPower: '24 kW' },
  { sequence: '36', name: '枕式包装机', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '12.50 kW', totalPower: '25 kW' },
  { sequence: '37', name: '包装流水线', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '7.50 kW', totalPower: '15 kW' },
  { sequence: '38', name: '筐桶清洗机', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '20 kW', totalPower: '40 kW' },
  { sequence: '39', name: '贴标机', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '5 kW', totalPower: '10 kW' },
  { sequence: '40', name: '光电分选设备', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '65 kW', totalPower: '65 kW' },
  { sequence: '41', name: '定重包装设备', area: '-', quantity: '3', defrostPower: '-', defrostTotal: '-', runningPower: '15 kW', totalPower: '45 kW' },
  { sequence: '42', name: '辅助辅联设备', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '40 kW', totalPower: '40 kW' },
  { sequence: '43', name: '空压机', area: '-', quantity: '1', defrostPower: '-', defrostTotal: '-', runningPower: '22 kW', totalPower: '22 kW' },
  { sequence: '44', name: '熏蒸设备', area: '-', quantity: '2', defrostPower: '-', defrostTotal: '-', runningPower: '15 kW', totalPower: '30 kW' }
])
const powerSummaryRows = ref([
  { name: '化霜总功率', basis: '按30% 同时化霜', totalPower: '249.09 kW' },
  { name: '设备运行功率', basis: '按90% 同时使用系数', totalPower: '819.14 kW' },
  { name: '制冷总功率', basis: '化霜同时系数30% + 设备运行同时系数90%', totalPower: '1068.23 kW' },
  { name: '生产设备总功率', basis: '按90% 同时使用系数', totalPower: '284.40 kW' },
  { name: '合计', basis: '', totalPower: '1352.63 kW' }
])
const totalPower = ref('1352.63 kW')
const totalDemandPower = ref('1352.63 kW')
const completenessRows = computed(() => [
  { item: '日处理量', value: `${designInputs.dailyInboundMassTons} t/day`, state: '已确认', owner: '工艺' },
  { item: '工作时长', value: `${designInputs.workingHoursPerDay} h/day`, state: '已确认', owner: '工艺' },
  { item: '成品库库存天数', value: `${designInputs.finishedStorageDays} 天`, state: '已确认', owner: '仓储' },
  { item: '主要包材库存天数', value: `${designInputs.packagingStorageDays} 天`, state: '已确认', owner: '仓储' },
  { item: '辅助包材库存天数', value: `${designInputs.auxiliaryPackagingStorageDays} 天`, state: '已确认', owner: '仓储' },
  { item: '原果暂存比例', value: `${designInputs.rawStorageRatio}`, state: '待复核', owner: '工艺' },
  { item: '一级预冷工作时间', value: `${designInputs.primaryPrecoolingWorkingHours} h`, state: '待复核', owner: '制冷' },
  { item: '二级预冷工作时间', value: `${designInputs.secondaryPrecoolingWorkingHours} h`, state: '待复核', owner: '制冷' },
  { item: '成品托位重量', value: `${designInputs.finishedGoodsPalletWeightKg} kg/托`, state: '待复核', owner: '仓储' },
  { item: '冻果比例', value: `${designInputs.frozenFruitRatio}`, state: '待复核', owner: '工艺' },
  { item: '冷间设计温度', value: '8~10℃ / 1~3℃ / -18℃', state: '待复核', owner: '制冷' },
  { item: '冻果托位重量', value: `${designInputs.frozenGoodsPalletWeightKg} kg/托`, state: '待复核', owner: '仓储' },
  { item: '设备功率参数', value: '参考莱富康表', state: '待复核', owner: '电气' }
])

const schemeRows = computed(() => {
  const data = schemeComparisonData.value
  if (!data) return []
  return data.schemes.map(s => ({
    name: s.scheme_name,
    roomMix: `房间 ${s.room_module_count} 个 · 门 ${s.door_count} 扇`,
    area: `${formatNumber(s.total_area_m2)} m²`,
    positions: `${s.total_position_count} 个`,
    score: s.total_score,
    feasible: s.feasible,
    recommended: data.recommended_scheme_code === s.scheme_code,
    requiresReview: s.requires_review,
    investment: formatNumber(s.investment_cny),
    power: `${formatNumber(s.installed_power_kw_e)} kW(e)`,
    note: s.feasible ? (data.recommended_scheme_code === s.scheme_code ? '推荐' : '可行') : '不可行'
  }))
})

const comparisonRows = computed(() => {
  const data = schemeComparisonData.value
  if (!data || data.schemes.length === 0) {
    return [
      { metric: '总分', balanced: '-', largeRoom: '-', smallRoom: '-', note: '后端方案数据' },
    ]
  }
  // Map by scheme_code — order-independent
  const byCode = Object.fromEntries(data.schemes.map(s => [s.scheme_code, s]))
  const b = byCode['balanced']
  const lr = byCode['consolidated_large_rooms']
  const sr = byCode['segmented_small_rooms']
  const fmt = (v: number | string) => formatNumber(Number(v) || 0)
  return [
    { metric: '总分', balanced: b?.total_score ?? '-', largeRoom: lr?.total_score ?? '-', smallRoom: sr?.total_score ?? '-', note: data.weight_set_name },
    { metric: '可行性', balanced: b?.feasible ? '✓' : '✗', largeRoom: lr?.feasible ? '✓' : '✗', smallRoom: sr?.feasible ? '✓' : '✗', note: '硬约束校验' },
    { metric: '面积 (m²)', balanced: fmt(b?.total_area_m2 ?? 0), largeRoom: fmt(lr?.total_area_m2 ?? 0), smallRoom: fmt(sr?.total_area_m2 ?? 0), note: '' },
    { metric: '板位', balanced: String(b?.total_position_count ?? 0), largeRoom: String(lr?.total_position_count ?? 0), smallRoom: String(sr?.total_position_count ?? 0), note: '' },
    { metric: '房间数', balanced: String(b?.room_module_count ?? 0), largeRoom: String(lr?.room_module_count ?? 0), smallRoom: String(sr?.room_module_count ?? 0), note: '' },
    { metric: '门数', balanced: String(b?.door_count ?? 0), largeRoom: String(lr?.door_count ?? 0), smallRoom: String(sr?.door_count ?? 0), note: '' },
    { metric: '投资 (CNY)', balanced: fmt(b?.investment_cny ?? 0), largeRoom: fmt(lr?.investment_cny ?? 0), smallRoom: fmt(sr?.investment_cny ?? 0), note: '' },
    { metric: '装机功率 kW(e)', balanced: fmt(b?.installed_power_kw_e ?? 0), largeRoom: fmt(lr?.installed_power_kw_e ?? 0), smallRoom: fmt(sr?.installed_power_kw_e ?? 0), note: '' },
    { metric: '推荐', balanced: data.recommended_scheme_code === 'balanced' ? '★' : '', largeRoom: data.recommended_scheme_code === 'consolidated_large_rooms' ? '★' : '', smallRoom: data.recommended_scheme_code === 'segmented_small_rooms' ? '★' : '', note: '' },
    { metric: '待复核', balanced: b?.requires_review ? '是' : '否', largeRoom: lr?.requires_review ? '是' : '否', smallRoom: sr?.requires_review ? '是' : '否', note: data.weight_set_status === 'unverified' ? '演示权重' : '' },
  ]
})

const knowledgeRows = [
  { title: '知识依据清单', type: '目录', status: '已生成', excerpt: '冷链设计边界、温区、库存天数、设备功率表' },
  { title: '蓝莓冷链演示资料', type: 'Markdown', status: '已解析', excerpt: '蓝莓采后预冷、低温分选包装、成品冷藏要点' },
  { title: '元谋冷库设备表', type: 'Excel', status: '已引用', excerpt: '制冷机组、冷风机、辅助设备、生产设备功率' },
  { title: '扫描版资料', type: 'PDF', status: 'requires_ocr', excerpt: 'V1 不做 OCR，保留复核标记' }
]

const reportRows = [
  { name: '方案书草稿', format: 'Word', status: '报告生成队列', source: '已持久化计算结果', owner: '设计负责人' },
  { name: '计算书草稿', format: 'Excel', status: '等待生成', source: '区域规划 + 用电配置', owner: '工程校核' },
  { name: '用电参数附表', format: 'Excel', status: '样例完成', source: '莱富康功率表', owner: '电气' }
]

const versionRows = [
  { version: 'v1', status: 'draft', change: '25 t/day 蓝莓加工中心演示项目', author: 'system seed' },
  { version: 'v1.1', status: 'locked', change: '项目、参数、计算结果持久化基线', author: 'Codex' },
  { version: 'v1.5', status: 'locked', change: '按参考 Excel 修正用电配置', author: 'Codex' }
]

const auditRows = [
  { time: '2026-06-18 10:12', action: 'create_project', target: '蓝莓加工中心演示项目', result: 'success' },
  { time: '2026-06-18 10:18', action: 'save_design_inputs', target: 'v1 draft', result: 'success' },
  { time: '2026-06-18 10:24', action: 'run_project_calculations', target: '区域规划 / 投资 / 用电', result: 'requires_review' },
  { time: '2026-06-18 10:31', action: 'generate_report_draft', target: '方案书草稿', result: 'queued' }
]

async function runPlanning(): Promise<void> {
  planningStatus.value = '正在生成规划...'
  planningError.value = ''
  const response = await fetch('/api/v1/demo/planning-run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      daily_inbound_mass_kg: designInputs.dailyInboundMassTons * 1000,
      working_time_h_per_day: designInputs.workingHoursPerDay,
      utilization_factor: 0.85,
      finished_storage_days: designInputs.finishedStorageDays,
      packaging_storage_days: designInputs.packagingStorageDays,
      main_packaging_storage_days: designInputs.packagingStorageDays,
      auxiliary_packaging_storage_days: designInputs.auxiliaryPackagingStorageDays,
      reserve_factor: 1.05,
      precooling_required_ratio: designInputs.precoolingRequiredRatio,
      primary_precooling_working_hours_per_day: designInputs.primaryPrecoolingWorkingHours,
      secondary_precooling_working_hours_per_day: designInputs.secondaryPrecoolingWorkingHours,
      raw_storage_ratio: designInputs.rawStorageRatio,
      finished_goods_pallet_weight_kg: designInputs.finishedGoodsPalletWeightKg,
      frozen_fruit_ratio: designInputs.frozenFruitRatio,
      frozen_storage_days: designInputs.frozenStorageDays,
      frozen_goods_pallet_weight_kg: designInputs.frozenGoodsPalletWeightKg
    })
  })
  const data = (await response.json()) as PlanningRunResponse
  if (!response.ok || !data.success) {
    planningError.value = '规划计算失败，请检查参数。'
    planningStatus.value = '等待重新生成'
    return
  }
  zoneRows.value = data.zone_plan.result.zones.map((zone) => ({
    zoneName: zone.zone_name,
    temperatureBand: zone.temperature_band,
    dailyThroughput: `${formatNumber(zone.daily_throughput_kg_day ?? zone.daily_throughput_kg ?? 0)} kg/day`,
    storageMass: zone.design_storage_mass_kg > 0 ? `${formatNumber(zone.design_storage_mass_kg)} kg` : '按周转配置',
    positions: String(zone.position_count),
    area: `${formatNumber(zone.required_area_m2)} m²`
  }))
  totalZoneArea.value = `${formatNumber(data.summary.total_area_m2)} m²`
  totalPositions.value = String(data.summary.total_position_count)
  totalInvestment.value = formatWan(data.summary.total_investment_cny)
  totalPower.value = `${formatNumber(data.summary.total_power_kw)} kW`
  investmentRows.value = data.investment_estimate.result.items.map((item) => ({
    itemName: item.item_name,
    amount: formatWan(item.amount_cny)
  }))
  powerRows.value = data.power_configuration.equipment_rows.map((item) => ({
    sequence: String(item.sequence),
    name: item.name,
    area: item.area || '-',
    quantity: formatNumber(item.quantity),
    defrostPower: formatOptionalPower(item.defrost_power_kw),
    defrostTotal: formatOptionalPower(item.defrost_total_power_kw),
    runningPower: `${formatNumber(item.running_power_kw)} kW`,
    totalPower: `${formatNumber(item.total_power_kw)} kW`
  }))
  powerSummaryRows.value = data.power_configuration.summary_rows.map((item) => ({
    name: item.name,
    basis: item.basis || '-',
    totalPower: `${formatNumber(item.total_power_kw)} kW`
  }))
  totalDemandPower.value = `${formatNumber(data.power_configuration.total_estimated_demand_kw)} kW`
  planningStatus.value = '规划已根据当前参数刷新'
}

async function loadSchemeComparison(): Promise<void> {
  schemeLoadError.value = ''
  try {
    const response = await fetch('/api/v1/demo/scheme-comparison')
    if (!response.ok) {
      schemeLoadError.value = '方案数据加载失败'
      return
    }
    schemeComparisonData.value = (await response.json()) as SchemeComparisonResponse
  } catch {
    schemeLoadError.value = '方案数据加载失败，请检查后端服务'
  }
}

// Load scheme data on mount
loadSchemeComparison()

function selectView(view: string): void {
  activeView.value = view
}

function formatWan(value: number): string {
  return `${(value / 10000).toFixed(2)} 万元`
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function formatOptionalPower(value: number | null): string {
  return value === null ? '-' : `${formatNumber(value)} kW`
}
</script>

<template>
  <main class="workspace-shell">
    <header class="app-topbar">
      <strong>冷库规划设计助手V1</strong>
      <div class="topbar-actions">
        <button
          class="ai-icon-button"
          type="button"
          aria-label="打开AI助手"
          @click="isAgentOpen = !isAgentOpen"
        >
          AI
        </button>
        <div v-if="isAgentOpen" class="agent-popover">
          <strong>AI 助手</strong>
          <div class="message">
            我可以提取需求、生成参数变更建议、调用确定性计算工具并解释结果。
          </div>
          <textarea
            aria-label="Agent消息"
            placeholder="输入自然语言需求，例如：日入库量调整为30吨"
          ></textarea>
          <button type="button">生成变更建议</button>
        </div>
      </div>
    </header>

    <section class="work-area">
      <nav class="workflow-nav" aria-label="主流程">
        <button
          v-for="step in workflowSteps"
          :key="step.label"
          :class="{ active: activeView === step.view }"
          type="button"
          @click="selectView(step.view)"
        >
          {{ step.label }}
        </button>
      </nav>

      <section
        v-if="activeView === '项目概览'"
        class="parameter-grid"
        aria-label="基本信息"
      >
        <div v-if="activeView === '项目概览'" class="overview-summary">
          <strong>总体情况</strong>
          <div class="overview-fields" aria-label="项目概览基础信息">
            <label>
              <span>加工厂名称</span>
              <input v-model.trim="factoryOverview.factoryName" aria-label="加工厂名称" type="text" />
            </label>
            <label>
              <span>定植亩数</span>
              <input
                v-model.number="factoryOverview.plantingAreaMu"
                aria-label="定植亩数"
                min="0"
                type="number"
              />
            </label>
            <label>
              <span>定植品种</span>
              <input v-model.trim="factoryOverview.mainVarieties" aria-label="定植品种" type="text" />
            </label>
          </div>
        </div>
        <form class="planning-form" @submit.prevent="runPlanning">
          <label class="planning-field field-normal">
            <span>日处理量</span>
            <input
              v-model.number="designInputs.dailyInboundMassTons"
              aria-label="日处理量"
              min="1"
              type="number"
            />
            <em>吨/天</em>
          </label>
          <label class="planning-field field-compact">
            <span>工作时长</span>
            <input
              v-model.number="designInputs.workingHoursPerDay"
              aria-label="工作时长"
              min="1"
              type="number"
            />
            <em>小时/天</em>
          </label>
          <label class="planning-field field-compact">
            <span>成品存储</span>
            <input
              v-model.number="designInputs.finishedStorageDays"
              aria-label="成品库库存天数"
              min="1"
              type="number"
            />
            <em>天</em>
          </label>
          <label class="planning-field field-compact">
            <span>包材库存</span>
            <input
              v-model.number="designInputs.packagingStorageDays"
              aria-label="包材库库存天数"
              min="1"
              type="number"
            />
            <em>天</em>
          </label>
          <label class="planning-field field-wide">
            <span>辅助包材库存</span>
            <input
              v-model.number="designInputs.auxiliaryPackagingStorageDays"
              aria-label="辅助包材库存天数"
              min="1"
              type="number"
            />
            <em>天</em>
          </label>
          <label class="planning-field field-normal">
            <span>原果暂存比例</span>
            <input
              v-model.number="designInputs.rawStorageRatio"
              aria-label="原果暂存比例"
              min="0.01"
              step="0.01"
              type="number"
            />
          </label>
          <label class="planning-field field-wide">
            <span>一级预冷工作</span>
            <input
              v-model.number="designInputs.primaryPrecoolingWorkingHours"
              aria-label="一级预冷工作时间"
              min="1"
              type="number"
            />
            <em>小时</em>
          </label>
          <label class="planning-field field-wide">
            <span>二级预冷工作</span>
            <input
              v-model.number="designInputs.secondaryPrecoolingWorkingHours"
              aria-label="二级预冷工作时间"
              min="1"
              type="number"
            />
            <em>小时</em>
          </label>
          <label class="planning-field field-normal">
            <span>成品托重</span>
            <input
              v-model.number="designInputs.finishedGoodsPalletWeightKg"
              aria-label="成品托位重量"
              min="1"
              type="number"
            />
            <em>kg/托</em>
          </label>
          <label class="planning-field field-compact">
            <span>冻果比例</span>
            <input
              v-model.number="designInputs.frozenFruitRatio"
              aria-label="冻果比例"
              min="0.01"
              step="0.01"
              type="number"
            />
          </label>
          <label class="planning-field field-normal">
            <span>冻果托重</span>
            <input
              v-model.number="designInputs.frozenGoodsPalletWeightKg"
              aria-label="冻果托位重量"
              min="1"
              type="number"
            />
            <em>kg/托</em>
          </label>
          <label class="planning-field field-compact">
            <span>冻果库存</span>
            <input
              v-model.number="designInputs.frozenStorageDays"
              aria-label="冻果库存天数"
              min="1"
              type="number"
            />
            <em>天</em>
          </label>
          <button class="run-planning" type="button" @click="runPlanning">生成规划</button>
          <strong class="planning-status">{{ planningStatus }}</strong>
          <strong v-if="planningError" class="error-text">{{ planningError }}</strong>
          <div class="planning-totals">
            <span>总面积 {{ totalZoneArea }}</span>
            <span>板位 {{ totalPositions }} 个</span>
            <span>投资 {{ totalInvestment }}</span>
            <span>装机 {{ totalPower }}</span>
          </div>
        </form>
      </section>

      <section
        v-else-if="activeView === '计算结果'"
        class="results-table"
        aria-label="计算结果"
      >
        <table class="calculation-table">
          <thead>
            <tr>
              <th>区域</th>
              <th>估算面积</th>
              <th>设计存储量</th>
              <th>板位数量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in zoneRows" :key="row.zoneName">
              <th scope="row">{{ row.zoneName }}</th>
              <td>{{ row.area }}</td>
              <td>{{ row.storageMass }}</td>
              <td>{{ row.positions }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">总面积合计</th>
              <td>{{ totalZoneArea }}</td>
              <td></td>
              <td>{{ totalPositions }}</td>
            </tr>
          </tfoot>
        </table>
      </section>

      <section
        v-else-if="activeView === '参数完整度'"
        class="sample-page"
        aria-label="参数完整度"
      >
        <div class="section-summary">
          <strong>参数完整度矩阵</strong>
          <span>已确认 4 项</span>
          <span>待复核 3 项</span>
          <em>概念阶段</em>
        </div>
        <article class="sample-row completeness-row sample-header">
          <strong>参数</strong>
          <strong>当前值</strong>
          <strong>状态</strong>
          <strong>责任专业</strong>
        </article>
        <article
          v-for="row in completenessRows"
          :key="row.item"
          class="sample-row completeness-row"
        >
          <strong>{{ row.item }}</strong>
          <span>{{ row.value }}</span>
          <span>{{ row.state }}</span>
          <span>{{ row.owner }}</span>
        </article>
      </section>

      <section
        v-else-if="activeView === '冷间区域规划'"
        class="zone-table"
        aria-label="冷间区域规划"
      >
        <div class="zone-summary">
          <strong>总估算面积</strong>
          <span>{{ totalZoneArea }}</span>
          <em>需复核</em>
        </div>
        <article class="zone-row zone-header">
          <strong>区域</strong>
          <strong>温区</strong>
          <strong>承担产量</strong>
          <strong>设计存储量</strong>
          <strong>板位数量</strong>
          <strong>估算面积</strong>
        </article>
        <article
          v-for="row in zoneRows"
          :key="row.zoneName"
          class="zone-row"
        >
          <strong>{{ row.zoneName }}</strong>
          <span>{{ row.temperatureBand }}</span>
          <span>{{ row.dailyThroughput }}</span>
          <span>{{ row.storageMass }}</span>
          <span>{{ row.positions }}</span>
          <span>{{ row.area }}</span>
        </article>
        <p class="review-note">
          当前区域面积和板位数量使用 demo / unverified 演示系数，requires_review=true，不能作为正式施工图或最终设备选型依据。板位合计 {{ totalPositions }} 个。
        </p>
      </section>

      <section
        v-else-if="activeView === '用电配置'"
        class="power-table"
        aria-label="用电配置"
      >
        <div class="power-summary">
          <strong>用电配置统计</strong>
          <span>装机 {{ totalPower }}</span>
          <span>合计 {{ totalDemandPower }}</span>
          <em>需复核</em>
        </div>
        <table class="power-config-table">
          <thead>
            <tr>
              <th>序号</th>
              <th>名称</th>
              <th>区域</th>
              <th>数量</th>
              <th>功率</th>
              <th>总功率</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in powerRows"
              :key="`${row.sequence}-${row.name}-${row.area}`"
            >
              <td>{{ row.sequence }}</td>
              <th scope="row">{{ row.name }}</th>
              <td>{{ row.area }}</td>
              <td>{{ row.quantity }}</td>
              <td>{{ row.runningPower }}</td>
              <td>{{ row.totalPower }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr v-for="row in powerSummaryRows" :key="row.name">
              <td></td>
              <th scope="row">{{ row.name }}</th>
              <td colspan="3">{{ row.basis }}</td>
              <td>{{ row.totalPower }}</td>
            </tr>
          </tfoot>
        </table>
        <p class="review-note">
          用电配置为概念阶段估算，不能替代正式电气设计、设备铭牌功率统计或供配电校核。
        </p>
      </section>

      <section
        v-else-if="activeView === '投资测算'"
        class="investment-table"
        aria-label="投资测算"
      >
        <div class="investment-summary">
          <strong>投资估算</strong>
          <span>{{ totalInvestment }}</span>
          <em>需复核</em>
        </div>
        <table class="investment-estimate-table">
          <thead>
            <tr>
              <th>投资分项</th>
              <th>估算金额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in investmentRows" :key="row.itemName">
              <th scope="row">{{ row.itemName }}</th>
              <td>{{ row.amount }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">合计</th>
              <td>{{ totalInvestment }}</td>
            </tr>
          </tfoot>
        </table>
        <p class="review-note">
          投资测算使用 demo / unverified 演示单价，未包含土地、税费、融资、正式设计费和专项工程费用。
        </p>
      </section>

      <section
        v-else-if="activeView === '冷间方案'"
        class="sample-page"
        aria-label="冷间方案"
      >
        <div class="section-summary">
          <strong>{{ schemeComparisonData?.recommended_scheme_code ? schemeRows.find(r => r.recommended)?.name ?? '方案' : '方案' }}</strong>
          <span>{{ schemeComparisonData ? schemeRows.length + ' 个方案' : '加载中...' }}</span>
          <em>{{ schemeComparisonData?.weight_set_name ?? '' }}</em>
          <span v-if="schemeLoadError" style="color:var(--danger)">{{ schemeLoadError }}</span>
        </div>
        <article class="sample-row scheme-row sample-header">
          <strong>方案</strong>
          <strong>房间/门</strong>
          <strong>面积</strong>
          <strong>板位</strong>
          <strong>评分</strong>
          <strong>投资</strong>
          <strong>kW(e)</strong>
          <strong>状态</strong>
        </article>
        <article
          v-for="row in schemeRows"
          :key="row.name"
          class="sample-row scheme-row"
        >
          <strong>{{ row.name }}{{ row.recommended ? ' ★' : '' }}</strong>
          <span>{{ row.roomMix }}</span>
          <span>{{ row.area }}</span>
          <span>{{ row.positions }}</span>
          <span>{{ row.score }}</span>
          <span>{{ row.investment }}</span>
          <span>{{ row.power }}</span>
          <span>{{ row.note }}{{ row.requiresReview ? ' (待复核)' : '' }}</span>
        </article>
      </section>

      <section
        v-else-if="activeView === '方案对比'"
        class="sample-page"
        aria-label="方案对比"
      >
        <div class="section-summary">
          <strong>方案评分对比</strong>
          <span>{{ schemeComparisonData?.weight_set_name ?? '后端方案数据' }}</span>
          <em>{{ schemeComparisonData?.weight_set_status === 'unverified' ? '演示权重 / 待复核' : '' }}</em>
        </div>
        <article class="sample-row comparison-row sample-header">
          <strong>指标</strong>
          <strong>{{ schemeRows[0]?.name ?? '方案A' }}</strong>
          <strong>{{ schemeRows[1]?.name ?? '方案B' }}</strong>
          <strong>{{ schemeRows[2]?.name ?? '方案C' }}</strong>
          <strong>备注</strong>
        </article>
        <article
          v-for="row in comparisonRows"
          :key="row.metric"
          class="sample-row comparison-row"
        >
          <strong>{{ row.metric }}</strong>
          <span>{{ row.balanced }}</span>
          <span>{{ row.largeRoom }}</span>
          <span>{{ row.smallRoom }}</span>
          <span>{{ row.note }}</span>
        </article>
      </section>

      <section
        v-else-if="activeView === '知识依据'"
        class="sample-page"
        aria-label="知识依据"
      >
        <div class="section-summary">
          <strong>知识依据清单</strong>
          <span>4 个来源</span>
          <span>混合检索样例</span>
          <em>待复核</em>
        </div>
        <article class="sample-row knowledge-row sample-header">
          <strong>资料</strong>
          <strong>类型</strong>
          <strong>状态</strong>
          <strong>摘要</strong>
        </article>
        <article
          v-for="row in knowledgeRows"
          :key="row.title"
          class="sample-row knowledge-row"
        >
          <strong>{{ row.title }}</strong>
          <span>{{ row.type }}</span>
          <span>{{ row.status }}</span>
          <span>{{ row.excerpt }}</span>
        </article>
      </section>

      <section
        v-else-if="activeView === '报告'"
        class="sample-page"
        aria-label="报告"
      >
        <div class="section-summary">
          <strong>报告生成队列</strong>
          <span>3 个交付物</span>
          <span>读取持久化结果</span>
          <em>草稿</em>
        </div>
        <article class="sample-row report-row sample-header">
          <strong>报告</strong>
          <strong>格式</strong>
          <strong>状态</strong>
          <strong>数据来源</strong>
          <strong>负责人</strong>
        </article>
        <article
          v-for="row in reportRows"
          :key="row.name"
          class="sample-row report-row"
        >
          <strong>{{ row.name }}</strong>
          <span>{{ row.format }}</span>
          <span>{{ row.status }}</span>
          <span>{{ row.source }}</span>
          <span>{{ row.owner }}</span>
        </article>
      </section>

      <section
        v-else-if="activeView === '版本历史'"
        class="sample-page"
        aria-label="版本历史"
      >
        <div class="section-summary">
          <strong>版本历史</strong>
          <span>v1 当前草稿</span>
          <span>不可变快照</span>
          <em>示例</em>
        </div>
        <article class="sample-row version-row sample-header">
          <strong>版本</strong>
          <strong>状态</strong>
          <strong>变更摘要</strong>
          <strong>创建者</strong>
        </article>
        <article
          v-for="row in versionRows"
          :key="row.version"
          class="sample-row version-row"
        >
          <strong>{{ row.version }}</strong>
          <span>{{ row.status }}</span>
          <span>{{ row.change }}</span>
          <span>{{ row.author }}</span>
        </article>
      </section>

      <section
        v-else-if="activeView === '审计记录'"
        class="sample-page"
        aria-label="审计记录"
      >
        <div class="section-summary">
          <strong>审计记录</strong>
          <span>4 条样例</span>
          <span>run_project_calculations</span>
          <em>可追溯</em>
        </div>
        <article class="sample-row audit-row sample-header">
          <strong>时间</strong>
          <strong>动作</strong>
          <strong>对象</strong>
          <strong>结果</strong>
        </article>
        <article
          v-for="row in auditRows"
          :key="`${row.time}-${row.action}`"
          class="sample-row audit-row"
        >
          <strong>{{ row.time }}</strong>
          <span>{{ row.action }}</span>
          <span>{{ row.target }}</span>
          <span>{{ row.result }}</span>
        </article>
      </section>

      <section v-else class="placeholder-panel">
        <h2>{{ activeView }}</h2>
        <p>该页面保留结构化操作入口，不以聊天作为唯一操作入口。</p>
      </section>
    </section>
  </main>
</template>
