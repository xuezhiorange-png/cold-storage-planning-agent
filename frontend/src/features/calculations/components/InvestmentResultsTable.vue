<script setup lang="ts">
import { computed } from 'vue'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import CalculationBasisDetails from './CalculationBasisDetails.vue'
import PersistedArrayResultsTable from './PersistedArrayResultsTable.vue'
import PersistedScalarResultsTable from './PersistedScalarResultsTable.vue'
import { INVESTMENT_ITEM_COLUMNS } from './persistedResultLabels'
import {
  EMPTY_STAGE_COPY,
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

const scalarFields = computed(() => {
  const data = payload.value
  if (!data) return []
  return [
    {
      label: '总投资',
      key: 'total_investment_cny',
      unit: '万元',
      value: formatPersistedWan(data.total_investment_cny).replace(' 万元', '')
    }
  ]
})

const itemRows = computed(() => persistedObjectRows(payload.value?.items))

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="investment-results" aria-label="投资估算结果">
    <p v-if="!hasPayload" class="investment-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <PersistedScalarResultsTable :fields="scalarFields" />

      <PersistedArrayResultsTable
        v-if="itemRows.length > 0"
        caption="投资分项"
        :rows="itemRows"
        :columns="INVESTMENT_ITEM_COLUMNS"
        value-format="wan"
      />

      <CalculationBasisDetails
        :formulas="formulas"
        :assumptions="assumptions"
        :warnings="warnings"
      />
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
</style>
