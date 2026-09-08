<script setup lang="ts">
import { computed } from 'vue'

import type {
  FactoryPowerCanonicalDetail,
  FactoryPowerCanonicalSummary,
  FactoryPowerPresentation
} from '../../../api/contracts/factoryPower'

const props = defineProps<{
  presentation: FactoryPowerPresentation | null
}>()

const summaryFields: Array<{ key: keyof FactoryPowerCanonicalSummary; label: string }> = [
  { key: 'defrost_installed_power_kw', label: '化霜装机功率' },
  { key: 'defrost_coincident_power_kw', label: '化霜计入功率' },
  { key: 'other_installed_power_kw', label: '其他设备装机功率' },
  { key: 'other_coincident_power_kw', label: '其他设备计入功率' },
  { key: 'production_equipment_installed_power_kw', label: '生产设备装机功率' },
  { key: 'production_equipment_coincident_power_kw', label: '生产设备计入功率' },
  { key: 'total_installed_power_kw', label: '总装机功率' },
  { key: 'estimated_total_power_kw', label: '估算工厂电功率' }
]

const summaryRows = computed(() => {
  if (!props.presentation) return []
  return summaryFields.map((field) => ({
    label: field.label,
    value: props.presentation?.summary[field.key]
  }))
})

function showValue(value: unknown): string {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function showPower(value: unknown): string {
  return `${showValue(value)} kW`
}

function showReview(review: Record<string, unknown>): string {
  return review.requires_review === true ? 'requires_review=true' : 'requires_review=false'
}

function showMetadata(value: Record<string, unknown>): string {
  return JSON.stringify(value)
}

function detailLabel(detail: FactoryPowerCanonicalDetail): string {
  return detail.display_label && detail.display_label !== detail.equipment_or_zone
    ? `${detail.display_label}（${detail.equipment_or_zone}）`
    : detail.equipment_or_zone
}

function poolLabel(detail: FactoryPowerCanonicalDetail): string {
  return detail.pool_label && detail.pool_label !== detail.pool
    ? `${detail.pool_label}（${detail.pool}）`
    : detail.pool
}
</script>

<template>
  <section class="factory-power-estimation" data-testid="factory-power-estimation-card">
    <div class="factory-power-estimation__header">
      <div>
        <h2>估算工厂电功率（V2.0）</h2>
        <p>只读呈现 factory_power_estimation@2.0.0-p1 canonical result</p>
      </div>
      <span v-if="presentation" class="factory-power-estimation__identity">
        {{ presentation.source_calculator_identity }}
      </span>
    </div>

    <div v-if="presentation" class="factory-power-estimation__body">
      <div class="factory-power-estimation__headline">
        <div>
          <span>估算工厂电功率</span>
          <strong>{{ showPower(presentation.summary.estimated_total_power_kw) }}</strong>
        </div>
        <div>
          <span>总装机功率</span>
          <strong>{{ showPower(presentation.summary.total_installed_power_kw) }}</strong>
        </div>
      </div>

      <div class="factory-power-estimation__meta">
        <span>面积档位：{{ presentation.factory_area_band }}</span>
        <span>canonical hash：{{ presentation.canonical_result_hash }}</span>
      </div>

      <div class="factory-power-estimation__review">
        <strong>工程复核：{{ showReview(presentation.review) }}</strong>
        <span>状态：{{ showValue(presentation.review.status) }}</span>
      </div>

      <div class="factory-power-estimation__section">
        <h3>三池汇总（kW）</h3>
        <table class="factory-power-estimation__table">
          <thead>
            <tr><th scope="col">功率池/指标</th><th scope="col">canonical 值</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in summaryRows" :key="row.label">
              <td>{{ row.label }}</td>
              <td>{{ showPower(row.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="factory-power-estimation__section">
        <h3>明细（原始 canonical 字段）</h3>
        <div class="factory-power-estimation__table-wrap">
          <table class="factory-power-estimation__table">
            <thead>
              <tr>
                <th scope="col">设备/区域</th>
                <th scope="col">计算依据</th>
                <th scope="col">数量</th>
                <th scope="col">单台功率</th>
                <th scope="col">装机功率</th>
                <th scope="col">功率池</th>
                <th scope="col">同时系数</th>
                <th scope="col">计入功率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="detail in presentation.details" :key="detail.equipment_or_zone">
                <td>{{ detailLabel(detail) }}</td>
                <td>{{ detail.basis }}</td>
                <td>{{ detail.configured_quantity }}</td>
                <td>{{ showPower(detail.unit_power_kw) }}</td>
                <td>{{ showPower(detail.installed_power_kw) }}</td>
                <td>{{ poolLabel(detail) }}</td>
                <td>{{ detail.simultaneity_factor }}</td>
                <td>{{ showPower(detail.coincident_power_kw) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="factory-power-estimation__section factory-power-estimation__audit">
        <h3>假设与来源</h3>
        <ul>
          <li v-for="assumption in presentation.assumptions" :key="assumption">
            {{ assumption }}
          </li>
        </ul>
        <p>provenance：{{ showMetadata(presentation.provenance) }}</p>
        <p>单位语义：{{ showMetadata(presentation.unit_semantics) }}</p>
      </div>
    </div>

    <div v-else class="factory-power-estimation__empty">
      <p>暂无可用的 V2.0 估算工厂电功率结果。</p>
      <p>当前版本未找到 factory_power_estimation@2.0.0-p1；不会回退到旧装机功率或补充用电配置。</p>
    </div>
  </section>
</template>

<style scoped>
.factory-power-estimation {
  border: 1px solid #d9e2ef;
  border-radius: 10px;
  background: #fff;
  padding: 18px;
}

.factory-power-estimation__header,
.factory-power-estimation__headline,
.factory-power-estimation__meta,
.factory-power-estimation__review {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.factory-power-estimation__header h2,
.factory-power-estimation__section h3 {
  margin: 0;
}

.factory-power-estimation__header p,
.factory-power-estimation__meta,
.factory-power-estimation__review,
.factory-power-estimation__audit p {
  color: #66758a;
  font-size: 13px;
}

.factory-power-estimation__identity {
  color: #2f6f95;
  font-family: monospace;
  font-size: 12px;
}

.factory-power-estimation__body {
  display: grid;
  gap: 18px;
  margin-top: 18px;
}

.factory-power-estimation__headline > div {
  display: grid;
  gap: 6px;
}

.factory-power-estimation__headline strong {
  color: #1f5f82;
  font-size: 24px;
}

.factory-power-estimation__section {
  display: grid;
  gap: 10px;
}

.factory-power-estimation__table-wrap {
  overflow-x: auto;
}

.factory-power-estimation__audit ul {
  margin: 0;
  padding-left: 20px;
}

.factory-power-estimation__empty {
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  color: #66758a;
  margin-top: 18px;
  padding: 24px;
  text-align: center;
}

.factory-power-estimation__empty p {
  margin: 4px 0;
}
</style>
