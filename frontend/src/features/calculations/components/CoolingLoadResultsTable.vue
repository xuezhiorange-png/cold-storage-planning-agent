<script setup lang="ts">
import { computed } from 'vue'

import type { CalculationRunRecord } from '../../../api/contracts/calculations'
import CalculationBasisDetails from './CalculationBasisDetails.vue'
import PersistedArrayResultsTable from './PersistedArrayResultsTable.vue'
import PersistedScalarResultsTable from './PersistedScalarResultsTable.vue'
import {
  COOLING_LEVEL_SUMMARY_COLUMNS,
  COOLING_LOAD_SCALAR_FIELDS,
  COOLING_ZONE_COLUMNS
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
  return COOLING_LOAD_SCALAR_FIELDS.map((field) => ({
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
  return []
})

const levelSummaryRows = computed(() => {
  const data = payload.value
  if (!data) return []
  const levelSummaries = persistedObjectRows(data.level_summaries)
  if (levelSummaries.length > 0) return levelSummaries
  return persistedObjectRows(data.temperature_levels)
})

const formulas = computed(() => readPersistedFormulas(props.record))
const assumptions = computed(() => readPersistedAssumptions(props.record))
const warnings = computed(() => readPersistedWarnings(props.record))
</script>

<template>
  <section class="cooling-load-results" aria-label="冷负荷结果">
    <p v-if="!hasPayload" class="cooling-load-results__empty">{{ EMPTY_STAGE_COPY }}</p>

    <template v-else>
      <PersistedScalarResultsTable :fields="scalarFields" />

      <PersistedArrayResultsTable
        v-if="zoneRows.length > 0"
        caption="分区冷负荷"
        :rows="zoneRows"
        :columns="COOLING_ZONE_COLUMNS"
      />

      <PersistedArrayResultsTable
        v-if="levelSummaryRows.length > 0"
        caption="温区汇总"
        :rows="levelSummaryRows"
        :columns="COOLING_LEVEL_SUMMARY_COLUMNS"
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
</style>
