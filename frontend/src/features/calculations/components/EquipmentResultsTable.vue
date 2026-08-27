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

const equipmentFields = computed(() => {
  const data = payload.value
  if (!data) return []
  return [
    { label: '蒸发器总制冷量', key: 'evaporator_total_cooling_capacity_kw', unit: 'kW' },
    { label: '蒸发器数量', key: 'evaporator_quantity', unit: '' },
    { label: '单台蒸发器容量', key: 'single_evaporator_capacity_kw', unit: 'kW' },
    { label: '压缩机运行容量', key: 'compressor_operating_capacity_kw', unit: 'kW' },
    { label: '备用容量', key: 'standby_capacity_kw', unit: 'kW' },
    { label: '冷凝器散热量', key: 'condenser_heat_rejection_capacity_kw', unit: 'kW' },
    { label: '蒸发温度', key: 'evaporation_temperature_c', unit: '℃' },
    { label: '冷凝温度', key: 'condensing_temperature_c', unit: '℃' },
    { label: '化霜方式', key: 'defrost_method', unit: '' }
  ].map((field) => ({
    ...field,
    value: formatPersistedNumber(data[field.key])
  }))
})

const systemRows = computed(() => persistedObjectRows(payload.value?.systems))
const systemRowKeys = computed(() => {
  const keys = new Set<string>()
  for (const row of systemRows.value) {
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
  <section class="equipment-results" aria-label="设备选型结果">
    <p v-if="!hasPayload" class="equipment-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <dl class="equipment-results__fields">
        <div v-for="field in equipmentFields" :key="field.key">
          <dt>{{ field.label }}</dt>
          <dd>
            {{ field.value }}
            <span v-if="field.unit">{{ field.unit }}</span>
          </dd>
        </div>
      </dl>

      <div v-if="systemRows.length > 0" class="table-scroll">
        <table class="equipment-results__table">
          <thead>
            <tr>
              <th v-for="key in systemRowKeys" :key="key" scope="col">{{ key }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in systemRows" :key="`system-row-${index}`">
              <td v-for="key in systemRowKeys" :key="`${index}-${key}`">
                {{ formatPersistedNumber(row[key]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section v-if="formulas.length > 0" class="equipment-results__extras">
        <h4>公式 (持久化)</h4>
        <ul>
          <li v-for="(formula, index) in formulas" :key="`formula-${index}`">
            <span v-if="formula.formula_id">{{ formula.formula_id }}: </span>
            <span v-if="formula.expression">{{ formula.expression }}</span>
            <span v-if="formula.description"> — {{ formula.description }}</span>
          </li>
        </ul>
      </section>

      <section v-if="assumptions.length > 0" class="equipment-results__extras">
        <h4>假设</h4>
        <ul>
          <li v-for="(assumption, index) in assumptions" :key="`assumption-${index}`">{{ assumption }}</li>
        </ul>
      </section>

      <section v-if="warnings.length > 0" class="equipment-results__extras equipment-results__extras--warnings">
        <h4>警告</h4>
        <ul>
          <li v-for="(warning, index) in warnings" :key="`warning-${index}`">{{ warning }}</li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.equipment-results__empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.equipment-results__fields {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 13px;
}

.equipment-results__fields div {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 8px;
}

.equipment-results__fields dt {
  margin: 0;
  color: #6b7a8f;
}

.equipment-results__fields dd {
  margin: 0;
  font-weight: 500;
}

.equipment-results__table {
  width: 100%;
  margin-top: 12px;
  border-collapse: collapse;
  font-size: 12px;
}

.equipment-results__table th,
.equipment-results__table td {
  border: 1px solid #d0d7e2;
  padding: 6px 8px;
  text-align: left;
}

.equipment-results__table th {
  background: #f3f7fb;
}

.equipment-results__extras {
  margin-top: 12px;
  font-size: 12px;
}

.equipment-results__extras h4 {
  margin: 0 0 4px;
  font-size: 13px;
}

.equipment-results__extras ul {
  margin: 0;
  padding-left: 18px;
}

.equipment-results__extras--warnings {
  color: #856404;
}
</style>
