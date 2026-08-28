<script setup lang="ts">
import { computed } from 'vue'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import CalculationBasisDetails from './CalculationBasisDetails.vue'
import PersistedArrayResultsTable from './PersistedArrayResultsTable.vue'
import PersistedScalarResultsTable from './PersistedScalarResultsTable.vue'
import {
  INSTALLED_POWER_SCALAR_FIELDS,
  POWER_EQUIPMENT_ROW_COLUMNS,
  POWER_ITEM_COLUMNS,
  POWER_SUMMARY_ROW_COLUMNS
} from './persistedResultLabels'
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
  return INSTALLED_POWER_SCALAR_FIELDS.map((field) => ({
    ...field,
    value: formatPersistedNumber(data[field.key])
  }))
})

const equipmentRows = computed(() => persistedObjectRows(payload.value?.equipment_rows))
const summaryRows = computed(() => persistedObjectRows(payload.value?.summary_rows))
const itemRows = computed(() => persistedObjectRows(payload.value?.items))

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="installed-power-results" aria-label="装机功率结果">
    <p v-if="!hasPayload" class="installed-power-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <PersistedScalarResultsTable :fields="scalarFields" />

      <PersistedArrayResultsTable
        v-if="equipmentRows.length > 0"
        caption="设备明细"
        :rows="equipmentRows"
        :columns="POWER_EQUIPMENT_ROW_COLUMNS"
        value-format="equipment_area"
      />

      <PersistedArrayResultsTable
        v-if="summaryRows.length > 0"
        caption="功率汇总"
        :rows="summaryRows"
        :columns="POWER_SUMMARY_ROW_COLUMNS"
      />

      <PersistedArrayResultsTable
        v-if="itemRows.length > 0"
        caption="需用功率分项"
        :rows="itemRows"
        :columns="POWER_ITEM_COLUMNS"
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
</style>
