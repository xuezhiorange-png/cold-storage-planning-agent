<script setup lang="ts">
import { computed } from 'vue'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import CalculationBasisDetails from './CalculationBasisDetails.vue'
import PersistedArrayResultsTable from './PersistedArrayResultsTable.vue'
import PersistedScalarResultsTable from './PersistedScalarResultsTable.vue'
import { EQUIPMENT_SCALAR_FIELDS, EQUIPMENT_SYSTEM_COLUMNS } from './persistedResultLabels'
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

const scalarFields = computed(() => {
  const data = payload.value
  if (!data) return []
  return EQUIPMENT_SCALAR_FIELDS.map((field) => ({
    ...field,
    value: formatPersistedNumber(data[field.key])
  }))
})

const systemRows = computed(() => persistedObjectRows(payload.value?.systems))

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="equipment-results" aria-label="设备选型结果">
    <p v-if="!hasPayload" class="equipment-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <PersistedScalarResultsTable :fields="scalarFields" />

      <PersistedArrayResultsTable
        v-if="systemRows.length > 0"
        caption="制冷系统"
        :rows="systemRows"
        :columns="EQUIPMENT_SYSTEM_COLUMNS"
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
</style>
