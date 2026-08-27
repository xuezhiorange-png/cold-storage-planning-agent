<script setup lang="ts">
import { computed } from 'vue'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import {
  EMPTY_STAGE_COPY,
  formatPersistedNumber,
  persistedObjectRows,
  readPersistedAssumptions,
  readPersistedFormulas,
  readPersistedResultPayload,
  readPersistedWarnings
} from '../model/mapPersistedCalculations'

const props = defineProps<{
  record: CalculationRunRecord | null
}>()

const payload = computed(() => readPersistedResultPayload(props.record))
const hasPayload = computed(() => payload.value !== null)

const loadFields = computed(() => {
  const data = payload.value
  if (!data) return []
  return [
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
  ].map((field) => ({
    ...field,
    value: formatPersistedNumber(data[field.key])
  }))
})

const zoneRows = computed(() => {
  const data = payload.value
  if (!data) return []
  const zones = persistedObjectRows(data.zones)
  if (zones.length > 0) return zones
  const zoneLoads = persistedObjectRows(data.zone_loads)
  if (zoneLoads.length > 0) return zoneLoads
  return persistedObjectRows(data.level_summaries)
})

const zoneRowKeys = computed(() => {
  const keys = new Set<string>()
  for (const row of zoneRows.value) {
    for (const key of Object.keys(row)) {
      keys.add(key)
    }
  }
  return Array.from(keys)
})

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="cooling-load-results" aria-label="冷负荷结果">
    <p v-if="!hasPayload" class="cooling-load-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <dl class="cooling-load-results__fields">
        <div v-for="field in loadFields" :key="field.key">
          <dt>{{ field.label }}</dt>
          <dd>{{ field.value }} {{ field.unit }}</dd>
        </div>
      </dl>

      <div v-if="zoneRows.length > 0" class="table-scroll">
        <table class="cooling-load-results__table">
          <thead>
            <tr>
              <th v-for="key in zoneRowKeys" :key="key" scope="col">{{ key }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in zoneRows" :key="`zone-row-${index}`">
              <td v-for="key in zoneRowKeys" :key="`${index}-${key}`">
                {{ formatPersistedNumber(row[key]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section v-if="formulas.length > 0" class="cooling-load-results__extras">
        <h4>公式 (持久化)</h4>
        <ul>
          <li v-for="(formula, index) in formulas" :key="`formula-${index}`">
            <span v-if="formula.formula_id">{{ formula.formula_id }}: </span>
            <span v-if="formula.expression">{{ formula.expression }}</span>
            <span v-if="formula.description"> — {{ formula.description }}</span>
          </li>
        </ul>
      </section>

      <section v-if="assumptions.length > 0" class="cooling-load-results__extras">
        <h4>假设</h4>
        <ul>
          <li v-for="(assumption, index) in assumptions" :key="`assumption-${index}`">{{ assumption }}</li>
        </ul>
      </section>

      <section v-if="warnings.length > 0" class="cooling-load-results__extras cooling-load-results__extras--warnings">
        <h4>警告</h4>
        <ul>
          <li v-for="(warning, index) in warnings" :key="`warning-${index}`">{{ warning }}</li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.cooling-load-results__empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.cooling-load-results__fields {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 13px;
}

.cooling-load-results__fields div {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 8px;
}

.cooling-load-results__fields dt {
  margin: 0;
  color: #6b7a8f;
}

.cooling-load-results__fields dd {
  margin: 0;
  font-weight: 500;
}

.cooling-load-results__table {
  width: 100%;
  margin-top: 12px;
  border-collapse: collapse;
  font-size: 12px;
}

.cooling-load-results__table th,
.cooling-load-results__table td {
  border: 1px solid #d0d7e2;
  padding: 6px 8px;
  text-align: left;
}

.cooling-load-results__table th {
  background: #f3f7fb;
}

.cooling-load-results__extras {
  margin-top: 12px;
  font-size: 12px;
}

.cooling-load-results__extras h4 {
  margin: 0 0 4px;
  font-size: 13px;
}

.cooling-load-results__extras ul {
  margin: 0;
  padding-left: 18px;
}

.cooling-load-results__extras--warnings {
  color: #856404;
}
</style>
