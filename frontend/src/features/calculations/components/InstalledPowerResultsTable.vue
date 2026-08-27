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

const totalInstalled = computed(() =>
  formatPersistedNumber(payload.value?.total_installed_power_kw_e)
)
const totalDemand = computed(() =>
  formatPersistedNumber(payload.value?.total_estimated_demand_kw)
)

const equipmentRows = computed(() => persistedObjectRows(payload.value?.equipment_rows))
const summaryRows = computed(() => persistedObjectRows(payload.value?.summary_rows))
const itemRows = computed(() => persistedObjectRows(payload.value?.items))

function rowKeys(rows: Array<Record<string, unknown>>): string[] {
  const keys = new Set<string>()
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      keys.add(key)
    }
  }
  return Array.from(keys)
}

const equipmentRowKeys = computed(() => rowKeys(equipmentRows.value))
const summaryRowKeys = computed(() => rowKeys(summaryRows.value))
const itemRowKeys = computed(() => rowKeys(itemRows.value))

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="installed-power-results" aria-label="装机功率结果">
    <p v-if="!hasPayload" class="installed-power-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <dl class="installed-power-results__totals">
        <div>
          <dt>装机总功率 (kW(e))</dt>
          <dd>{{ totalInstalled }}</dd>
        </div>
        <div>
          <dt>估算需求功率 (kW)</dt>
          <dd>{{ totalDemand }}</dd>
        </div>
      </dl>

      <div v-if="equipmentRows.length > 0" class="table-scroll">
        <h4 class="installed-power-results__subheading">设备明细 (equipment_rows)</h4>
        <table class="installed-power-results__table">
          <thead>
            <tr>
              <th v-for="key in equipmentRowKeys" :key="key" scope="col">{{ key }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in equipmentRows" :key="`equipment-row-${index}`">
              <td v-for="key in equipmentRowKeys" :key="`${index}-${key}`">
                {{ formatPersistedNumber(row[key]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="summaryRows.length > 0" class="table-scroll">
        <h4 class="installed-power-results__subheading">汇总行 (summary_rows)</h4>
        <table class="installed-power-results__table">
          <thead>
            <tr>
              <th v-for="key in summaryRowKeys" :key="key" scope="col">{{ key }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in summaryRows" :key="`summary-row-${index}`">
              <td v-for="key in summaryRowKeys" :key="`${index}-${key}`">
                {{ formatPersistedNumber(row[key]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="itemRows.length > 0" class="table-scroll">
        <h4 class="installed-power-results__subheading">分项 (items)</h4>
        <table class="installed-power-results__table">
          <thead>
            <tr>
              <th v-for="key in itemRowKeys" :key="key" scope="col">{{ key }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in itemRows" :key="`item-row-${index}`">
              <td v-for="key in itemRowKeys" :key="`${index}-${key}`">
                {{ formatPersistedNumber(row[key]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section v-if="formulas.length > 0" class="installed-power-results__extras">
        <h4>公式 (持久化)</h4>
        <ul>
          <li v-for="(formula, index) in formulas" :key="`formula-${index}`">
            <span v-if="formula.formula_id">{{ formula.formula_id }}: </span>
            <span v-if="formula.expression">{{ formula.expression }}</span>
            <span v-if="formula.description"> — {{ formula.description }}</span>
          </li>
        </ul>
      </section>

      <section v-if="assumptions.length > 0" class="installed-power-results__extras">
        <h4>假设</h4>
        <ul>
          <li v-for="(assumption, index) in assumptions" :key="`assumption-${index}`">{{ assumption }}</li>
        </ul>
      </section>

      <section v-if="warnings.length > 0" class="installed-power-results__extras installed-power-results__extras--warnings">
        <h4>警告</h4>
        <ul>
          <li v-for="(warning, index) in warnings" :key="`warning-${index}`">{{ warning }}</li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.installed-power-results__empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.installed-power-results__totals {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 13px;
}

.installed-power-results__totals div {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 8px;
}

.installed-power-results__totals dt {
  margin: 0;
  color: #6b7a8f;
}

.installed-power-results__totals dd {
  margin: 0;
  font-weight: 600;
}

.installed-power-results__subheading {
  margin: 12px 0 6px;
  font-size: 13px;
}

.installed-power-results__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.installed-power-results__table th,
.installed-power-results__table td {
  border: 1px solid #d0d7e2;
  padding: 6px 8px;
  text-align: left;
}

.installed-power-results__table th {
  background: #f3f7fb;
}

.installed-power-results__extras {
  margin-top: 12px;
  font-size: 12px;
}

.installed-power-results__extras h4 {
  margin: 0 0 4px;
  font-size: 13px;
}

.installed-power-results__extras ul {
  margin: 0;
  padding-left: 18px;
}

.installed-power-results__extras--warnings {
  color: #856404;
}
</style>
