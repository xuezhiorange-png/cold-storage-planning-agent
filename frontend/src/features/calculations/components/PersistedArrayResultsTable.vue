<script setup lang="ts">
import { computed } from 'vue'

import { formatPersistedNumber, formatPersistedWan } from '../model/mapPersistedCalculations'
import type { PersistedColumnDef } from './persistedResultLabels'
import { formatEquipmentArea } from './persistedResultLabels'

const props = defineProps<{
  rows: Array<Record<string, unknown>>
  columns: PersistedColumnDef[]
  caption?: string
  valueFormat?: 'number' | 'wan' | 'equipment_area'
}>()

const visibleColumns = computed(() =>
  props.columns.filter((column) =>
    props.rows.some((row) => row[column.key] !== undefined && row[column.key] !== null)
  )
)

function formatCell(row: Record<string, unknown>, column: PersistedColumnDef): string {
  const value = row[column.key]
  if (value === undefined || value === null) return '—'
  if (props.valueFormat === 'wan' && column.key === 'amount_cny') {
    return formatPersistedWan(value)
  }
  if (props.valueFormat === 'equipment_area' && column.key === 'area') {
    return formatEquipmentArea(value)
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatPersistedNumber(item)).join('、')
  }
  return formatPersistedNumber(value)
}
</script>

<template>
  <div v-if="rows.length > 0 && visibleColumns.length > 0" class="persisted-array-table-wrap">
    <h4 v-if="caption" class="persisted-array-table__caption">{{ caption }}</h4>
    <div class="table-scroll">
      <table class="persisted-array-table">
        <thead>
          <tr>
            <th
              v-for="column in visibleColumns"
              :key="column.key"
              scope="col"
            >
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="`row-${index}`">
            <td
              v-for="column in visibleColumns"
              :key="`${index}-${column.key}`"
            >
              {{ formatCell(row, column) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.persisted-array-table__caption {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
}

.persisted-array-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.persisted-array-table th,
.persisted-array-table td {
  border: 1px solid #d0d7e2;
  padding: 6px 8px;
  text-align: left;
}

.persisted-array-table th {
  background: #f3f7fb;
  font-weight: 600;
}
</style>
