<script setup lang="ts">
import { computed } from 'vue'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import {
  EMPTY_STAGE_COPY,
  formatPersistedNumber,
  formatPersistedWan,
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

const totalInvestment = computed(() =>
  formatPersistedWan(payload.value?.total_investment_cny)
)

const itemRows = computed(() => persistedObjectRows(payload.value?.items))

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="investment-results" aria-label="投资估算结果">
    <p v-if="!hasPayload" class="investment-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <div class="investment-results__total">
        <strong>总投资</strong>
        <span>{{ totalInvestment }}</span>
      </div>

      <div v-if="itemRows.length > 0" class="table-scroll">
        <table class="investment-results__table">
          <thead>
            <tr>
              <th scope="col">投资分项</th>
              <th scope="col">估算金额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in itemRows" :key="`item-row-${index}`">
              <td>{{ formatPersistedNumber(row.item_name) }}</td>
              <td>{{ formatPersistedWan(row.amount_cny) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <section v-if="formulas.length > 0" class="investment-results__extras">
        <h4>公式 (持久化)</h4>
        <ul>
          <li v-for="(formula, index) in formulas" :key="`formula-${index}`">
            <span v-if="formula.formula_id">{{ formula.formula_id }}: </span>
            <span v-if="formula.expression">{{ formula.expression }}</span>
            <span v-if="formula.description"> — {{ formula.description }}</span>
          </li>
        </ul>
      </section>

      <section v-if="assumptions.length > 0" class="investment-results__extras">
        <h4>假设</h4>
        <ul>
          <li v-for="(assumption, index) in assumptions" :key="`assumption-${index}`">{{ assumption }}</li>
        </ul>
      </section>

      <section v-if="warnings.length > 0" class="investment-results__extras investment-results__extras--warnings">
        <h4>警告</h4>
        <ul>
          <li v-for="(warning, index) in warnings" :key="`warning-${index}`">{{ warning }}</li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.investment-results__empty {
  margin: 0;
  padding: 16px;
  text-align: center;
  color: #6b7a8f;
  border: 1px dashed #d0d7e2;
  border-radius: 8px;
  background: #f8f9fb;
  font-size: 14px;
}

.investment-results__total {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 16px;
  border: 1px solid #123a63;
  border-radius: 6px;
  background: #f3f7fb;
  font-size: 16px;
}

.investment-results__total strong {
  color: #0b1f3a;
}

.investment-results__total span {
  font-weight: 700;
  font-size: 18px;
}

.investment-results__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.investment-results__table th,
.investment-results__table td {
  border: 1px solid #d0d7e2;
  padding: 8px 10px;
  text-align: left;
}

.investment-results__table th {
  background: #f3f7fb;
}

.investment-results__table td:last-child {
  text-align: right;
}

.investment-results__extras {
  margin-top: 12px;
  font-size: 12px;
}

.investment-results__extras h4 {
  margin: 0 0 4px;
  font-size: 13px;
}

.investment-results__extras ul {
  margin: 0;
  padding-left: 18px;
}

.investment-results__extras--warnings {
  color: #856404;
}
</style>
